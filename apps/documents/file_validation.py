"""Validación técnica de un archivo cargado, antes de guardarlo (REQUERIMIENTOS §9.5).

- **MIME real por firma de bytes**, no por lo que declara el navegador. La lista es
  cerrada (``ALLOWED_MIME_TYPES``), así que no hace falta ``libmagic``.
- **Extensión coherente con el MIME detectado.** Se rechazan las dobles extensiones
  peligrosas (``cedula.pdf.exe``, ``foto.png.pdf``) y las extensiones ejecutables. Un
  punto en el nombre no basta para rechazar: ``certificado.v2.pdf`` es válido.
- **MIME declarado incoherente.** Si el navegador declara un tipo concreto distinto del
  detectado, se rechaza; ``application/octet-stream`` o vacío no dicen nada y se aceptan.
- **Tamaño.** Se lee por bloques y se corta en cuanto supera el máximo del tipo.
- **Nombre.** Sin ruta, sin caracteres de control, en NFC y de 255 caracteres como máximo.

El análisis antivirus llega después, de forma asíncrona (``scanning.py``).
"""

import hashlib
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import BinaryIO

from rest_framework.exceptions import ValidationError

from apps.documents.constants import JPEG, PDF, PNG
from apps.documents.exceptions import FileTooLarge, UnsupportedFileType

CHUNK_SIZE = 64 * 1024
MAX_FILENAME_LENGTH = 255

# Firmas de inicio de archivo.
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    PDF: (b"%PDF-",),
    JPEG: (b"\xff\xd8\xff",),
    PNG: (b"\x89PNG\r\n\x1a\n",),
}
_SIGNATURE_LENGTH = max(len(signature) for options in SIGNATURES.values() for signature in options)

EXTENSIONS: dict[str, frozenset[str]] = {
    PDF: frozenset({"pdf"}),
    JPEG: frozenset({"jpg", "jpeg"}),
    PNG: frozenset({"png"}),
}

# Lo que el navegador puede declarar para cada tipo.
DECLARED_ALIASES: dict[str, frozenset[str]] = {
    PDF: frozenset({PDF, "application/x-pdf"}),
    JPEG: frozenset({JPEG, "image/jpg", "image/pjpeg"}),
    PNG: frozenset({PNG, "image/x-png"}),
}
UNINFORMATIVE_DECLARED = frozenset({"", "application/octet-stream", "binary/octet-stream"})

# Extensiones que delatan un archivo ejecutable o interpretable por el navegador.
BLOCKED_EXTENSIONS = frozenset(
    {
        "apk", "app", "bat", "bin", "cmd", "com", "cpl", "dll", "dmg", "exe", "hta", "htm",
        "html", "jar", "js", "jse", "lnk", "msi", "php", "pif", "ps1", "py", "reg", "scr",
        "sh", "svg", "vb", "vbe", "vbs", "ws", "wsf", "xhtml",
    }
)  # fmt: skip
_KNOWN_EXTENSIONS = BLOCKED_EXTENSIONS.union(*EXTENSIONS.values())


@dataclass(frozen=True)
class InspectedFile:
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str


def _file_error(message: str) -> ValidationError:
    return ValidationError({"file": [message]})


def _detail(code: str, message: str) -> list[dict[str, str]]:
    return [{"field": "file", "code": code, "message": message}]


def sanitize_filename(raw: str) -> str:
    """Nombre seguro para guardar y mostrar. ``400`` si no queda nada usable."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    # Los espacios (también tabuladores y saltos) se colapsan; el resto de caracteres de
    # control o de formato se eliminan.
    name = "".join(char for char in name if char.isspace() or unicodedata.category(char)[0] != "C")
    name = " ".join(name.split()).strip(" .")
    if not name:
        raise _file_error("El archivo no tiene un nombre válido.")
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and 0 < len(extension) < 16:
            name = f"{stem[: MAX_FILENAME_LENGTH - len(extension) - 1]}.{extension}"
        else:
            name = name[:MAX_FILENAME_LENGTH]
    return name


def _extensions(filename: str) -> list[str]:
    """Extensiones del nombre en minúsculas, de la primera a la última."""
    return [part.lower() for part in filename.split(".")[1:]]


def detect_mime_type(head: bytes) -> str | None:
    for mime_type, signatures in SIGNATURES.items():
        if any(head.startswith(signature) for signature in signatures):
            return mime_type
    return None


def _check_extension(filename: str, mime_type: str) -> None:
    extensions = _extensions(filename)
    if not extensions or extensions[-1] not in EXTENSIONS[mime_type]:
        allowed = ", ".join(sorted(EXTENSIONS[mime_type]))
        raise UnsupportedFileType(
            details=_detail(
                "EXTENSION_MISMATCH",
                f"La extensión del archivo no corresponde a su contenido ({allowed}).",
            )
        )
    if any(extension in _KNOWN_EXTENSIONS for extension in extensions[:-1]):
        raise UnsupportedFileType(
            details=_detail("DOUBLE_EXTENSION", "El nombre del archivo tiene doble extensión.")
        )


def _check_declared(declared: str | None, mime_type: str) -> None:
    value = (declared or "").split(";", 1)[0].strip().lower()
    if value in UNINFORMATIVE_DECLARED or value in DECLARED_ALIASES[mime_type]:
        return
    raise UnsupportedFileType(
        details=_detail(
            "DECLARED_TYPE_MISMATCH",
            "El tipo que informa el navegador no coincide con el contenido del archivo.",
        )
    )


def _read(stream: BinaryIO, max_size_bytes: int) -> tuple[bytes, int, str]:
    """Primeros bytes, tamaño y SHA-256, leyendo por bloques. Corta al superar el máximo."""
    digest = hashlib.sha256()
    head = b""
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        size += len(chunk)
        if size > max_size_bytes:
            raise FileTooLarge(
                details=_detail(
                    "FILE_TOO_LARGE", f"El máximo para este documento es {max_size_bytes} bytes."
                )
            )
        if len(head) < _SIGNATURE_LENGTH:
            head += chunk[: _SIGNATURE_LENGTH - len(head)]
        digest.update(chunk)
    stream.seek(0)
    return head, size, digest.hexdigest()


def inspect_upload(
    stream: BinaryIO,
    *,
    filename: str,
    declared_mime_type: str | None,
    allowed_mime_types: Sequence[str],
    max_size_bytes: int,
) -> InspectedFile:
    """Valida el archivo y devuelve su nombre saneado, MIME real, tamaño y huella.

    Deja ``stream`` al inicio para guardarlo después. Errores: ``400`` (sin nombre o
    vacío), ``422 FILE_TOO_LARGE`` y ``422 UNSUPPORTED_FILE_TYPE``.
    """
    clean_name = sanitize_filename(filename)
    if any(extension in BLOCKED_EXTENSIONS for extension in _extensions(clean_name)):
        raise UnsupportedFileType(
            details=_detail("BLOCKED_EXTENSION", "Los archivos ejecutables no están permitidos.")
        )
    head, size, sha256 = _read(stream, max_size_bytes)
    if size == 0:
        raise _file_error("El archivo está vacío.")

    mime_type = detect_mime_type(head)
    if mime_type is None:
        raise UnsupportedFileType(
            details=_detail("UNKNOWN_CONTENT", "El contenido no es un PDF, JPEG ni PNG válido.")
        )
    if mime_type not in allowed_mime_types:
        allowed = ", ".join(allowed_mime_types)
        raise UnsupportedFileType(
            details=_detail(
                "TYPE_NOT_ALLOWED", f"Este documento solo admite estos formatos: {allowed}."
            )
        )
    _check_extension(clean_name, mime_type)
    _check_declared(declared_mime_type, mime_type)
    return InspectedFile(filename=clean_name, mime_type=mime_type, size_bytes=size, sha256=sha256)
