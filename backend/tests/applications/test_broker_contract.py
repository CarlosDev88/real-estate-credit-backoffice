"""Contrato de solicitudes para el broker (TAREA-brechas-3-demo, parte 1): `GET
/applications`, `GET /applications/{id}` y `GET /clients/{id}/applications` describen las
dos formas (`anyOf`, ver SEC-21), como `/clients`. Los componentes que el front ya usa no cambian."""

from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

from tests.applications.test_applications_api import SUMMARY_KEYS

APPLICATIONS = "/api/v1/applications"
APPLICATION = "/api/v1/applications/{application_id}"
CLIENT_APPLICATIONS = "/api/v1/clients/{client_id}/applications"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return dict(SchemaGenerator().get_schema(request=None, public=True))


def ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def body_schema(schema: dict[str, Any], path: str, method: str, code: str) -> dict[str, Any]:
    response = schema["paths"][path][method]["responses"][code]
    return dict(response["content"]["application/json"]["schema"])


def test_the_application_responses_describe_both_shapes(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    for path in (APPLICATIONS, CLIENT_APPLICATIONS):
        assert body_schema(schema, path, "get", "200") == ref("PaginatedApplicationListByRole")
    assert components["PaginatedApplicationListByRole"]["anyOf"] == [
        ref("PaginatedApplicationList"),
        ref("PaginatedApplicationSummaryList"),
    ]
    assert components["PaginatedApplicationList"]["properties"]["items"]["items"] == ref(
        "Application"
    )
    assert components["PaginatedApplicationSummaryList"]["properties"]["items"]["items"] == ref(
        "ApplicationSummary"
    )
    assert body_schema(schema, APPLICATION, "get", "200") == ref("ApplicationDetailByRole")
    assert components["ApplicationDetailByRole"]["anyOf"] == [
        ref("ApplicationDetail"),
        ref("ApplicationSummary"),
    ]
    # Lo que de verdad recibe el broker (`test_applications_api`) es `ApplicationSummary`.
    assert set(components["ApplicationSummary"]["properties"]) == SUMMARY_KEYS


def test_the_application_list_keeps_its_query_parameters(schema: dict[str, Any]) -> None:
    names = {p["name"] for p in schema["paths"][APPLICATIONS]["get"]["parameters"]}

    assert {"status", "quick_filter", "search", "ordering", "page", "page_size"} <= names
    client_names = {p["name"] for p in schema["paths"][CLIENT_APPLICATIONS]["get"]["parameters"]}
    assert client_names == {"client_id", "status", "page", "page_size"}
