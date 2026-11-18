"""Contrato OpenAPI de clientes y oportunidades (TAREA-brechas-2, parte 1): el broker
tiene su forma documentada y los componentes que el front ya usa no cambian de nombre."""

from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

from tests.crm.test_clients_api import BROKER_CLIENT_FIELDS

CLIENTS = "/api/v1/clients"
CLIENT = "/api/v1/clients/{client_id}"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return dict(SchemaGenerator().get_schema(request=None, public=True))


def ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def response(schema: dict[str, Any], path: str, method: str, code: str) -> dict[str, Any]:
    return dict(schema["paths"][path][method]["responses"][code])


def body_schema(schema: dict[str, Any], path: str, method: str, code: str) -> dict[str, Any]:
    return dict(response(schema, path, method, code)["content"]["application/json"]["schema"])


def test_client_responses_describe_both_shapes(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    assert body_schema(schema, CLIENTS, "get", "200") == ref("PaginatedClientListByRole")
    assert components["PaginatedClientListByRole"]["oneOf"] == [
        ref("PaginatedClientList"),
        ref("PaginatedBrokerClientList"),
    ]
    assert components["PaginatedClientList"]["properties"]["items"]["items"] == ref("Client")
    assert components["PaginatedBrokerClientList"]["properties"]["items"]["items"] == ref(
        "BrokerClient"
    )
    assert body_schema(schema, CLIENTS, "post", "201") == ref("ClientByRole")
    assert components["ClientByRole"]["oneOf"] == [ref("Client"), ref("BrokerClient")]
    for method in ("get", "patch"):
        assert body_schema(schema, CLIENT, method, "200") == ref("ClientDetailByRole")
    assert components["ClientDetailByRole"]["oneOf"] == [ref("ClientDetail"), ref("BrokerClient")]
    assert set(components["BrokerClient"]["properties"]) == BROKER_CLIENT_FIELDS


def test_client_list_keeps_its_query_parameters(schema: dict[str, Any]) -> None:
    names = {p["name"] for p in schema["paths"][CLIENTS]["get"]["parameters"]}

    assert names == {"document_type", "origin", "ordering", "search", "page", "page_size"}


def test_applications_count_is_optional_in_client(schema: dict[str, Any]) -> None:
    client = schema["components"]["schemas"]["Client"]

    assert client["properties"]["applications_count"]["type"] == "integer"
    assert "applications_count" not in client["required"]


def test_duplicate_document_describes_the_existing_client(schema: dict[str, Any]) -> None:
    for path, method in ((CLIENTS, "post"), (CLIENT, "patch")):
        description = response(schema, path, method, "409")["description"]
        assert "DUPLICATE_CLIENT_DOCUMENT" in description
        assert "resource_id" in description
    detail = schema["components"]["schemas"]["ErrorDetail"]
    assert "resource_id" in detail["properties"]


def test_opportunity_detail_is_typed(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]
    detail = components["OpportunityDetail"]["properties"]

    assert detail["available_actions"]["items"] == ref("OpportunityAvailableAction")
    assert detail["assignments"]["items"] == ref("OpportunityAssignment")
    assert set(components["OpportunityAvailableAction"]["required"]) == {
        "code",
        "label",
        "kind",
        "target_status",
        "target_status_label",
        "reason_required",
    }
    assert set(components["OpportunityAssignment"]["properties"]) == {
        "id",
        "advisor",
        "assigned_by",
        "reason",
        "created_at",
        "ended_at",
    }
    for name in ("Opportunity", "OpportunityDetail"):
        assert "status_label" in components[name]["required"]
    assert "reason_required" in components["AvailableAction"]["required"]
    assert "notes" in components["OpportunityCreateRequest"]["properties"]
