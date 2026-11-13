"""Transiciones de la radicación (Parte 1).

- `START_LEGALIZATION` y `MARK_READY_TO_REFILE` son manuales, por `/status-transitions`.
- `FILE` y `BANK_*` son de sistema: `/status-transitions` las rechaza (`409`) y las
  acciones disponibles no las listan.
"""

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.catalogs.exceptions import InvalidStateTransition
from apps.catalogs.services import resolve_transition
from apps.catalogs.workflow import ApplicationStatus, FlowType
from apps.documents.models import ApplicationDocumentSlot, SlotStatus
from apps.filings.models import FilingResponseObservation
from apps.identity.models import User
from tests.applications.conftest import application_url
from tests.applications.dossier.conftest import approve_required_slots
from tests.applications.filings.conftest import ObservationFactory
from tests.applications.test_property_financing_api import PROPERTY, bank_credit, put
from tests.applications.test_status_api import set_status, transition
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

TRANSITIONS_URL = "/api/v1/workflow-transitions"


@pytest.fixture
def ready_data(advisor_client: APIClient, application: CreditApplication) -> CreditApplication:
    """Inmueble, crédito bancario y todos los documentos obligatorios aprobados
    (versión 3)."""
    assert put(advisor_client, application, "property", PROPERTY).status_code == 201
    assert put(advisor_client, application, "financing", bank_credit(), '"2"').status_code == 201
    assert approve_required_slots(application)
    application.refresh_from_db()
    return application


@pytest.fixture
def observed(ready_data: CreditApplication) -> CreditApplication:
    set_status(ready_data, ApplicationStatus.BANK_OBSERVATION)
    return ready_data


def actions(client: APIClient, application: CreditApplication) -> list[str]:
    response = client.get(application_url(application, "/available-actions"))
    assert response.status_code == 200, response.content
    return [action["code"] for action in response.json()]


def last_history(application: CreditApplication) -> ApplicationStatusHistory:
    return (
        ApplicationStatusHistory.objects.filter(application=application)
        .select_related("transition")
        .latest("created_at")
    )


# --- START_LEGALIZATION -----------------------------------------------------------------


def test_start_legalization_from_approved(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.APPROVED)

    response = transition(advisor_client, application, "LEGALIZATION")

    assert response.status_code == 200, response.content
    assert response.json()["previous_status"] == "APPROVED"
    application.refresh_from_db()
    assert (application.status, application.version) == ("LEGALIZATION", 2)
    history = last_history(application)
    assert history.transition is not None
    assert history.transition.code == "START_LEGALIZATION"


@pytest.mark.parametrize("status", ["FILED", "CREDIT_ANALYSIS", "BANK_OBSERVATION"])
def test_legalization_only_starts_from_approved(
    advisor_client: APIClient, application: CreditApplication, status: str
) -> None:
    set_status(application, status)

    assert_error(
        transition(advisor_client, application, "LEGALIZATION"), 409, "INVALID_STATE_TRANSITION"
    )


def test_legalization_respects_the_scope(
    other_advisor_client: APIClient, broker_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.APPROVED)

    assert transition(other_advisor_client, application, "LEGALIZATION").status_code == 404
    assert transition(broker_client, application, "LEGALIZATION").status_code in (403, 404)
    application.refresh_from_db()
    assert application.status == ApplicationStatus.APPROVED


# --- MARK_READY_TO_REFILE ---------------------------------------------------------------


def test_refile_with_documents_and_no_open_observation(
    advisor_client: APIClient, observed: CreditApplication
) -> None:
    response = transition(advisor_client, observed, "READY_TO_FILE", version=observed.version)

    assert response.status_code == 200, response.content
    observed.refresh_from_db()
    assert observed.status == ApplicationStatus.READY_TO_FILE
    assert observed.ready_to_file_at is not None
    history = last_history(observed)
    assert history.transition is not None
    assert (history.from_status, history.transition.code) == (
        "BANK_OBSERVATION",
        "MARK_READY_TO_REFILE",
    )


def test_refile_lists_pending_documents_and_open_observations(
    advisor_client: APIClient, observed: CreditApplication, make_observation: ObservationFactory
) -> None:
    slots = list(ApplicationDocumentSlot.objects.filter(application=observed, is_required=True))
    rejected, approved_but_observed = slots[0], slots[1]
    ApplicationDocumentSlot.objects.filter(pk=rejected.pk).update(status=SlotStatus.REJECTED)
    make_observation(rejected)
    make_observation(approved_but_observed)

    response = transition(advisor_client, observed, "READY_TO_FILE", version=observed.version)

    body = assert_error(response, 422, "APPLICATION_NOT_READY")
    assert [(detail["code"], detail.get("resource_id")) for detail in body["details"]] == [
        ("DOCUMENT_PENDING", str(rejected.pk)),
        ("BANK_OBSERVATION_OPEN", str(rejected.pk)),
        ("BANK_OBSERVATION_OPEN", str(approved_but_observed.pk)),
    ]
    observed.refresh_from_db()
    assert observed.status == ApplicationStatus.BANK_OBSERVATION


def test_refile_after_the_observation_is_resolved(
    advisor_client: APIClient,
    observed: CreditApplication,
    make_observation: ObservationFactory,
) -> None:
    slot = ApplicationDocumentSlot.objects.filter(application=observed, is_required=True).first()
    assert slot is not None and slot.current_file is not None
    observation = make_observation(slot)
    blocked = transition(advisor_client, observed, "READY_TO_FILE", version=observed.version)
    assert [detail["code"] for detail in blocked.json()["details"]] == ["BANK_OBSERVATION_OPEN"]

    FilingResponseObservation.objects.filter(pk=observation.pk).update(
        resolved_by_file=slot.current_file, resolved_at=observation.created_at
    )

    response = transition(advisor_client, observed, "READY_TO_FILE", version=observed.version)
    assert response.status_code == 200, response.content


def test_refile_needs_the_bank_rules_and_product(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.BANK_OBSERVATION)

    body = assert_error(
        transition(advisor_client, application, "READY_TO_FILE"), 422, "APPLICATION_NOT_READY"
    )
    codes = [detail["code"] for detail in body["details"]]
    assert codes[0] == "BANK_PRODUCT_REQUIRED"
    assert "BANK_OBSERVATION_OPEN" not in codes


# --- Transiciones de sistema ------------------------------------------------------------


SYSTEM_MOVES = [
    ("READY_TO_FILE", "FILED"),
    ("FILED", "FILING_VALIDATION"),
    ("FILED", "CREDIT_ANALYSIS"),
    ("FILING_VALIDATION", "CREDIT_ANALYSIS"),
    ("CREDIT_ANALYSIS", "BANK_OBSERVATION"),
    ("CREDIT_ANALYSIS", "APPROVED"),
    ("FILED", "REJECTED"),
    ("BANK_OBSERVATION", "REJECTED"),
    ("LEGALIZATION", "DISBURSED"),
]


@pytest.mark.parametrize(("status", "target"), SYSTEM_MOVES)
@pytest.mark.parametrize("client_name", ["advisor_client", "admin_client"])
def test_status_transitions_rejects_system_transitions(
    request: pytest.FixtureRequest,
    application: CreditApplication,
    client_name: str,
    status: str,
    target: str,
) -> None:
    client: APIClient = request.getfixturevalue(client_name)
    set_status(application, status)

    assert_error(transition(client, application, target), 409, "INVALID_STATE_TRANSITION")
    application.refresh_from_db()
    assert (application.status, application.version) == (status, 1)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("FILED", ["WITHDRAW_FILED"]),
        ("FILING_VALIDATION", ["WITHDRAW_FILING_VALIDATION"]),
        ("CREDIT_ANALYSIS", ["WITHDRAW_CREDIT_ANALYSIS"]),
        ("BANK_OBSERVATION", ["MARK_READY_TO_REFILE", "WITHDRAW_BANK_OBSERVATION"]),
        ("APPROVED", ["START_LEGALIZATION", "WITHDRAW_APPROVED"]),
        ("LEGALIZATION", ["WITHDRAW_LEGALIZATION"]),
    ],
)
def test_available_actions_hide_system_transitions(
    advisor_client: APIClient,
    admin_client: APIClient,
    application: CreditApplication,
    status: str,
    expected: list[str],
) -> None:
    set_status(application, status)

    assert actions(advisor_client, application) == expected
    assert actions(admin_client, application) == expected


def test_ready_to_file_actions_do_not_offer_filing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.READY_TO_FILE)

    codes = actions(advisor_client, application)
    assert "FILE" not in codes
    assert "REOPEN_REVIEW" in codes


def test_refile_action_shows_its_guard(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.BANK_OBSERVATION)

    body = advisor_client.get(application_url(application, "/available-actions")).json()
    assert body[0] == {
        "code": "MARK_READY_TO_REFILE",
        "label": "Lista para radicar de nuevo",
        "target_status": "READY_TO_FILE",
        "guard_code": "APPLICATION_READY_TO_REFILE",
    }


def test_the_module_service_resolves_system_transitions(
    advisor_user: User, broker_user: User, make_user: Callable[..., User]
) -> None:
    def resolve(user: User, from_status: str, to_status: str, **extra: Any) -> str:
        return resolve_transition(
            user,
            flow_type=FlowType.APPLICATION,
            from_status=from_status,
            to_status=to_status,
            **extra,
        ).code

    assert resolve(advisor_user, "READY_TO_FILE", "FILED", system_only=True) == "FILE"
    assert resolve(advisor_user, "FILED", "CREDIT_ANALYSIS", system_only=True) == (
        "BANK_IN_ANALYSIS_FILED"
    )
    superuser = make_user(email="root@example.com", role_code=None, is_superuser=True)
    assert resolve(superuser, "LEGALIZATION", "DISBURSED", system_only=True) == "BANK_DISBURSED"
    # Una manual no se resuelve como de sistema, y al revés.
    with pytest.raises(InvalidStateTransition):
        resolve(advisor_user, "APPROVED", "LEGALIZATION", system_only=True)
    with pytest.raises(InvalidStateTransition):
        resolve(advisor_user, "READY_TO_FILE", "FILED")
    # El broker no tiene el rol de la transición.
    with pytest.raises(PermissionDenied):
        resolve(broker_user, "READY_TO_FILE", "FILED", system_only=True)


def test_transition_catalog_shows_system_only(admin_client: APIClient) -> None:
    body = admin_client.get(
        TRANSITIONS_URL, {"flow_type": "APPLICATION", "page_size": "100"}
    ).json()
    flags = {item["code"]: item["system_only"] for item in body["items"]}

    assert flags["FILE"] is True
    assert flags["BANK_DISBURSED"] is True
    assert flags["START_LEGALIZATION"] is False
    assert flags["MARK_READY_TO_FILE"] is False
