"""Cliente de clamd (INSTREAM) contra un servidor TCP falso, y escáner falso EICAR."""

import io
import socket
import socketserver
import struct
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.documents.exceptions import ScannerUnavailable
from apps.documents.models import ScanStatus
from apps.documents.scanning import (
    EICAR,
    EICAR_SIGNATURE,
    ClamdScanner,
    FakeScanner,
    ScanResult,
    get_scanner,
    parse_clamd_reply,
    validate_scanner_settings,
)


class FakeClamd(socketserver.BaseRequestHandler):
    """Implementa lo justo de clamd: ``zPING`` e ``zINSTREAM``.

    ``server.mode`` cambia la respuesta: ``normal``, ``error`` (límite de tamaño),
    ``silent`` (cierra sin responder) o ``wrong_pong``.
    """

    server: Any

    def _read_exactly(self, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = self.request.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return data

    def _read_command(self) -> bytes:
        command = b""
        while not command.endswith(b"\0"):
            chunk = self.request.recv(1)
            if not chunk:
                break
            command += chunk
        return command

    def handle(self) -> None:
        command = self._read_command()
        mode = self.server.mode
        if command == b"zPING\0":
            self.request.sendall(b"PONG\0" if mode != "wrong_pong" else b"PANG\0")
            return
        received = b""
        while True:
            (length,) = struct.unpack("!L", self._read_exactly(4))
            if length == 0:
                break
            received += self._read_exactly(length)
        self.server.received.append(received)
        if mode == "silent":
            return
        if mode == "error":
            self.request.sendall(b"INSTREAM size limit exceeded. ERROR\0")
        elif EICAR in received:
            self.request.sendall(b"stream: Win.Test.EICAR_HDB-1 FOUND\0")
        else:
            self.request.sendall(b"stream: OK\0")


class FakeClamdServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeClamd)
        self.mode = "normal"
        self.received: list[bytes] = []
        self.port: int = self.socket.getsockname()[1]


@pytest.fixture
def clamd() -> Iterator[FakeClamdServer]:
    server = FakeClamdServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def scanner_for(server: FakeClamdServer) -> ClamdScanner:
    return ClamdScanner(host="127.0.0.1", port=server.port, timeout=5)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


# --- Respuestas de clamd ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("stream: OK", ScanResult(ScanStatus.CLEAN)),
        ("stream: Eicar-Signature FOUND", ScanResult(ScanStatus.INFECTED, "Eicar-Signature")),
        ("stream: Win.Trojan.Agent-1 FOUND", ScanResult(ScanStatus.INFECTED, "Win.Trojan.Agent-1")),
    ],
)
def test_parse_clamd_reply(reply: str, expected: ScanResult) -> None:
    assert parse_clamd_reply(reply) == expected


@pytest.mark.parametrize("reply", ["INSTREAM size limit exceeded. ERROR", "", "stream: ???"])
def test_any_other_reply_fails_closed(reply: str) -> None:
    with pytest.raises(ScannerUnavailable):
        parse_clamd_reply(reply)


# --- ClamdScanner -------------------------------------------------------------------------


def test_clean_file_is_streamed_in_chunks(clamd: FakeClamdServer) -> None:
    content = b"%PDF-1.7\n" + b"x" * (200 * 1024)

    result = scanner_for(clamd).scan(io.BytesIO(content))

    assert result == ScanResult(ScanStatus.CLEAN)
    assert clamd.received == [content]


def test_eicar_is_reported_as_infected(clamd: FakeClamdServer) -> None:
    result = scanner_for(clamd).scan(io.BytesIO(b"%PDF-1.7\n" + EICAR))

    assert result == ScanResult(ScanStatus.INFECTED, "Win.Test.EICAR_HDB-1")


@pytest.mark.parametrize("mode", ["error", "silent"])
def test_clamd_errors_keep_the_file_pending(clamd: FakeClamdServer, mode: str) -> None:
    clamd.mode = mode

    with pytest.raises(ScannerUnavailable):
        scanner_for(clamd).scan(io.BytesIO(b"%PDF-1.7"))


def test_unreachable_clamd_is_unavailable() -> None:
    scanner = ClamdScanner(host="127.0.0.1", port=free_port(), timeout=1)

    with pytest.raises(ScannerUnavailable):
        scanner.scan(io.BytesIO(b"%PDF-1.7"))
    with pytest.raises(ScannerUnavailable):
        scanner.ping()


def test_connection_dropped_while_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenConnection:
        def __enter__(self) -> "BrokenConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def sendall(self, data: bytes) -> None:
            raise BrokenPipeError

    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: BrokenConnection())
    scanner = ClamdScanner(host="clamav", port=3310, timeout=1)

    with pytest.raises(ScannerUnavailable, match="análisis"):
        scanner.scan(io.BytesIO(b"%PDF-1.7"))
    with pytest.raises(ScannerUnavailable, match="PING"):
        scanner.ping()


def test_ping(clamd: FakeClamdServer) -> None:
    scanner_for(clamd).ping()

    clamd.mode = "wrong_pong"
    with pytest.raises(ScannerUnavailable, match="PONG"):
        scanner_for(clamd).ping()


# --- FakeScanner y configuración ----------------------------------------------------------


def test_fake_scanner_only_flags_eicar() -> None:
    scanner = FakeScanner()
    scanner.ping()

    assert scanner.scan(io.BytesIO(b"%PDF-1.7")) == ScanResult(ScanStatus.CLEAN)
    assert scanner.scan(io.BytesIO(b"%PDF-1.7\n" + EICAR)) == ScanResult(
        ScanStatus.INFECTED, EICAR_SIGNATURE
    )


def test_get_scanner_follows_the_settings() -> None:
    assert isinstance(get_scanner(), FakeScanner)

    with override_settings(DOCUMENT_SCANNER="clamd", CLAMD_HOST="clamav", CLAMD_PORT=3310):
        scanner = get_scanner()
    assert isinstance(scanner, ClamdScanner)
    assert (scanner.host, scanner.port, scanner.name) == ("clamav", 3310, "clamd")


def test_scanner_settings_are_validated() -> None:
    validate_scanner_settings()

    with override_settings(DOCUMENT_SCANNER="virustotal"), pytest.raises(ImproperlyConfigured):
        validate_scanner_settings()
    with (
        override_settings(DEBUG=False, DOCUMENT_ALLOW_FAKE_SERVICES=False),
        pytest.raises(ImproperlyConfigured, match="fake"),
    ):
        validate_scanner_settings()
    with override_settings(DEBUG=True, DOCUMENT_ALLOW_FAKE_SERVICES=False):
        validate_scanner_settings()
    with override_settings(DOCUMENT_SCANNER="clamd", DOCUMENT_ALLOW_FAKE_SERVICES=False):
        validate_scanner_settings()
