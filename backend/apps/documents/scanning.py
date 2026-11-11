"""Análisis antivirus de los archivos cargados (REQUERIMIENTOS §8.8 y §9.5).

- ``ClamdScanner``: cliente propio de ``clamd`` por TCP con el comando ``INSTREAM``,
  sin dependencias. El archivo viaja por bloques precedidos de su longitud (4 bytes,
  big-endian) y termina con un bloque de longitud cero.
- ``FakeScanner``: marca ``INFECTED`` la firma de prueba EICAR y ``CLEAN`` todo lo
  demás. Solo se admite con ``DEBUG`` o en pruebas; si no, Django no arranca.

**Falla cerrado.** Si ``clamd`` no responde o devuelve un error, se lanza
``ScannerUnavailable`` y el archivo sigue ``PENDING``: nunca pasa a ``CLEAN`` sin un
análisis real.
"""

import socket
import struct
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.documents.exceptions import ScannerUnavailable
from apps.documents.models import ScanStatus
from apps.documents.storage import fake_services_allowed

CLAMD = "clamd"
FAKE = "fake"
SCANNERS = (CLAMD, FAKE)

# Archivo de prueba estándar de los antivirus (no es malware).
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
EICAR_SIGNATURE = "Eicar-Test-Signature"

_CHUNK_SIZE = 64 * 1024
_MAX_REPLY = 4096


@dataclass(frozen=True)
class ScanResult:
    status: ScanStatus
    # Nombre de la firma detectada, solo con `INFECTED`.
    signature: str | None = None


class Scanner(Protocol):
    name: str

    def scan(self, stream: BinaryIO) -> ScanResult: ...

    def ping(self) -> None:
        """``ScannerUnavailable`` si el antivirus no responde."""
        ...


def parse_clamd_reply(reply: str) -> ScanResult:
    """``stream: OK`` → limpio; ``stream: <firma> FOUND`` → infectado; otro → error."""
    body = reply.removeprefix("stream:").strip()
    if body == "OK":
        return ScanResult(ScanStatus.CLEAN)
    if body.endswith(" FOUND"):
        return ScanResult(ScanStatus.INFECTED, body.removesuffix(" FOUND").strip())
    raise ScannerUnavailable(f"clamd respondió con un error: {body[:200]}")


class ClamdScanner:
    name = CLAMD

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def _connect(self) -> socket.socket:
        try:
            return socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise ScannerUnavailable("No se pudo conectar con clamd.") from exc

    @staticmethod
    def _read_reply(connection: socket.socket) -> str:
        """Lee hasta el terminador ``\\0`` (comandos con prefijo ``z``)."""
        data = b""
        while not data.endswith(b"\0") and len(data) < _MAX_REPLY:
            chunk = connection.recv(1024)
            if not chunk:
                break
            data += chunk
        return data.rstrip(b"\0").decode("utf-8", "replace").strip()

    def scan(self, stream: BinaryIO) -> ScanResult:
        with self._connect() as connection:
            try:
                connection.sendall(b"zINSTREAM\0")
                while chunk := stream.read(_CHUNK_SIZE):
                    connection.sendall(struct.pack("!L", len(chunk)) + chunk)
                connection.sendall(struct.pack("!L", 0))
                reply = self._read_reply(connection)
            except OSError as exc:
                raise ScannerUnavailable("clamd cortó la conexión durante el análisis.") from exc
        return parse_clamd_reply(reply)

    def ping(self) -> None:
        with self._connect() as connection:
            try:
                connection.sendall(b"zPING\0")
                reply = self._read_reply(connection)
            except OSError as exc:
                raise ScannerUnavailable("clamd no respondió al PING.") from exc
        if reply != "PONG":
            raise ScannerUnavailable("clamd no respondió PONG.")


class FakeScanner:
    name = FAKE

    def scan(self, stream: BinaryIO) -> ScanResult:
        if EICAR in stream.read():
            return ScanResult(ScanStatus.INFECTED, EICAR_SIGNATURE)
        return ScanResult(ScanStatus.CLEAN)

    def ping(self) -> None:
        return None


def validate_scanner_settings() -> None:
    """Falla al arrancar si la configuración no es segura (``ImproperlyConfigured``)."""
    scanner = settings.DOCUMENT_SCANNER
    if scanner not in SCANNERS:
        raise ImproperlyConfigured(f"DOCUMENT_SCANNER debe ser uno de {SCANNERS}.")
    if scanner == FAKE and not fake_services_allowed():
        raise ImproperlyConfigured("DOCUMENT_SCANNER=fake solo se admite con DEBUG o en pruebas.")


def get_scanner() -> Scanner:
    if settings.DOCUMENT_SCANNER == FAKE:
        return FakeScanner()
    return ClamdScanner(
        host=settings.CLAMD_HOST,
        port=settings.CLAMD_PORT,
        timeout=settings.CLAMD_TIMEOUT_SECONDS,
    )
