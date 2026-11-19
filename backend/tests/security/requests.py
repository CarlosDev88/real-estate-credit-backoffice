"""Cómo se arma cada petición de la matriz: cliente por actor, URL con ids del lado A,
cabeceras y cuerpo mínimo."""

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

from rest_framework.test import APIClient

from apps.applications.demo_data import demo_pdf
from apps.identity.cookies import access_cookie_name, buyer_session_cookie_name
from tests.security.conftest import ANON, BUYER_OTHER, BUYER_OWNER, World

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"
if not CONTRACT.exists():  # En el contenedor de pruebas, el contrato se monta en /contracts.
    CONTRACT = Path("/contracts/openapi.json")

METHODS = ("get", "post", "put", "patch", "delete")
_PARAM = re.compile(r"{(\w+)}")
# Cargas: multipart con un PDF pequeño (el resto de las escrituras va con JSON).
MULTIPART_OPERATIONS = {
    "POST /api/v1/buyer/document-slots/{slot_id}/uploads",
    "POST /api/v1/filing-responses/{response_id}/evidence",
}


def contract_operations() -> list[str]:
    """Todas las operaciones del contrato, como ``"MÉTODO /ruta"``."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return [
        f"{method.upper()} {path}"
        for path, item in spec["paths"].items()
        for method in METHODS
        if method in item
    ]


def client_for(world: World, actor: str) -> APIClient:
    client = APIClient()
    if actor in (BUYER_OWNER, BUYER_OTHER):
        side = world.a if actor == BUYER_OWNER else world.b
        client.cookies[buyer_session_cookie_name()] = side.buyer_token
    elif actor != ANON:
        client.cookies[access_cookie_name()] = world.access_tokens[actor]
    return client


def url_for(world: World, operation: str, ids: dict[str, str] | None = None) -> str:
    _, path = operation.split(" ", 1)
    values = {**world.path_ids(), **(ids or {})}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "job_id":
            name = "export_job_id" if "report-export-jobs" in path else "package_job_id"
        return values[name]

    return _PARAM.sub(replace, path)


def send(
    client: APIClient,
    operation: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> Any:
    method = operation.split(" ", 1)[0].lower()
    headers = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4()), "HTTP_IF_MATCH": '"1"'}
    if method in ("get", "delete"):
        return getattr(client, method)(url, **headers)
    if operation in MULTIPART_OPERATIONS:
        upload = io.BytesIO(demo_pdf("Matriz de acceso"))
        upload.name = "matriz.pdf"
        data = {"file": upload, **(body or {})}
        return getattr(client, method)(url, data, format="multipart", **headers)
    return getattr(client, method)(url, body or {}, format="json", **headers)
