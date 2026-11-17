"""El contrato declara ``ETag`` donde el backend lo envía (API §6)."""

from collections.abc import Iterator
from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

from config.openapi import etag_response_headers

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return dict(SchemaGenerator().get_schema(request=None, public=True))


def operations(schema: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def requires_if_match(operation: dict[str, Any]) -> bool:
    return any(
        parameter.get("in") == "header" and parameter.get("name") == "If-Match"
        for parameter in operation.get("parameters", [])
    )


def success_codes(operation: dict[str, Any]) -> list[str]:
    return [code for code in operation["responses"] if code.startswith("2")]


def declares_etag(response: dict[str, Any]) -> bool:
    header = response.get("headers", {}).get("ETag")
    return header is not None and header["schema"] == {"type": "string"}


def test_every_if_match_operation_declares_etag_in_its_2xx_responses(
    schema: dict[str, Any],
) -> None:
    checked = 0
    for path, method, operation in operations(schema):
        if not requires_if_match(operation):
            continue
        checked += 1
        for code in success_codes(operation):
            assert declares_etag(operation["responses"][code]), f"{method.upper()} {path} {code}"
    assert checked >= 10


def test_the_read_before_an_edit_declares_etag(schema: dict[str, Any]) -> None:
    """El cliente toma el ``ETag`` del ``GET`` del mismo recurso para mandar ``If-Match``."""
    for path, _, operation in operations(schema):
        if not requires_if_match(operation) or "get" not in schema["paths"][path]:
            continue
        read = schema["paths"][path]["get"]
        assert declares_etag(read["responses"]["200"]), f"GET {path}"


def test_etag_is_never_a_request_parameter(schema: dict[str, Any]) -> None:
    for path, method, operation in operations(schema):
        names = {parameter.get("name") for parameter in operation.get("parameters", [])}
        assert "ETag" not in names, f"{method.upper()} {path}"


def test_conditional_catalog_reads_declare_etag_on_200_and_304(schema: dict[str, Any]) -> None:
    for path in (
        "/api/v1/metadata/bootstrap",
        "/api/v1/metadata/catalogs/{catalog_code}",
        "/api/v1/buyer/metadata/catalogs/{catalog_code}",
    ):
        responses = schema["paths"][path]["get"]["responses"]
        assert declares_etag(responses["200"]) and declares_etag(responses["304"]), path


def test_the_helper_needs_at_least_one_code() -> None:
    with pytest.raises(ValueError):
        etag_response_headers()
