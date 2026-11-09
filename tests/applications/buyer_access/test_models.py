"""Restricciones de PostgreSQL y estado derivado del acceso del comprador (DER §4.9 a §4.12)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.utils import timezone

from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.identity.models import (
    BuyerAccessLink,
    BuyerAccessLinkStatus,
    BuyerSession,
    ConsentAction,
    ConsentDefinition,
    ConsentRecord,
    User,
    buyer_access_link_status_filter,
    consent_content_hash,
)

pytestmark = pytest.mark.django_db


def assert_violates(constraint: str, create: Callable[[], Any]) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        create()
    assert constraint in str(error.value)


# --- buyer_access_links -----------------------------------------------------------------


def test_link_status_is_derived_from_its_dates(
    make_link: Callable[..., BuyerAccessLink],
) -> None:
    now = timezone.now()
    # El CHECK impide un vencimiento anterior a la creación: el vencido se mira en el futuro.
    moment = now + timedelta(hours=2)
    pending = make_link(expires_at=now + timedelta(hours=72))
    expired = make_link(expires_at=now + timedelta(hours=1))
    consumed = make_link(consumed_at=now)
    revoked = make_link(revoked_at=now)

    assert pending.status == BuyerAccessLinkStatus.PENDING
    assert expired.status == BuyerAccessLinkStatus.PENDING
    assert expired.status_at(moment) == BuyerAccessLinkStatus.EXPIRED
    assert consumed.status == BuyerAccessLinkStatus.CONSUMED
    assert revoked.status == BuyerAccessLinkStatus.REVOKED

    for link in (pending, expired, consumed, revoked):
        status = link.status_at(moment)
        matches = BuyerAccessLink.objects.filter(buyer_access_link_status_filter(status, moment))
        assert list(matches) == [link]


def test_a_consumed_link_reports_consumed_even_after_expiring(
    make_link: Callable[..., BuyerAccessLink],
) -> None:
    link = make_link(consumed_at=timezone.now())
    later = link.expires_at + timedelta(days=1)

    assert link.status_at(later) == BuyerAccessLinkStatus.CONSUMED


def test_link_expiry_must_be_after_creation(make_link: Callable[..., BuyerAccessLink]) -> None:
    assert_violates(
        "ck_buyer_access_links_expiry",
        lambda: make_link(expires_at=timezone.now() - timedelta(minutes=1)),
    )


def test_a_link_cannot_be_consumed_and_revoked(make_link: Callable[..., BuyerAccessLink]) -> None:
    now = timezone.now()
    assert_violates(
        "ck_buyer_access_links_terminal",
        lambda: make_link(consumed_at=now, revoked_at=now),
    )


def test_link_token_hashes_are_unique(make_link: Callable[..., BuyerAccessLink]) -> None:
    make_link(token_hash="a" * 64)
    assert_violates("token_hash", lambda: make_link(token_hash="a" * 64))


def test_an_application_with_links_cannot_be_deleted(
    make_link: Callable[..., BuyerAccessLink], application: CreditApplication
) -> None:
    make_link()
    with pytest.raises(RestrictedError):
        application.delete()


# --- buyer_sessions ---------------------------------------------------------------------


def test_session_is_active_until_it_expires_or_is_revoked(
    make_session: Callable[..., BuyerSession],
) -> None:
    session = make_session()
    assert session.is_active_at()
    assert not session.is_active_at(session.expires_at)

    session.revoked_at = timezone.now()
    assert not session.is_active_at()


def test_session_expiry_must_be_after_creation(make_session: Callable[..., BuyerSession]) -> None:
    assert_violates(
        "ck_buyer_sessions_expiry",
        lambda: make_session(expires_at=timezone.now() - timedelta(minutes=1)),
    )


def test_a_link_opens_at_most_one_session(
    make_link: Callable[..., BuyerAccessLink], make_session: Callable[..., BuyerSession]
) -> None:
    link = make_link(consumed_at=timezone.now())
    make_session(access_link=link)
    assert_violates("access_link_id", lambda: make_session(access_link=link))


def test_session_token_hashes_are_unique(make_session: Callable[..., BuyerSession]) -> None:
    make_session(session_token_hash="b" * 64)
    assert_violates("session_token_hash", lambda: make_session(session_token_hash="b" * 64))


def test_a_link_with_a_session_cannot_be_deleted(
    make_session: Callable[..., BuyerSession],
) -> None:
    session = make_session()
    with pytest.raises(RestrictedError):
        session.access_link.delete()


# --- consent_definitions ----------------------------------------------------------------


def make_definition(**extra: Any) -> ConsentDefinition:
    extra.setdefault("code", "TEST_CONSENT")
    extra.setdefault("version", 1)
    extra.setdefault("title", "Consentimiento de prueba")
    extra.setdefault("body", "Texto de prueba.")
    extra.setdefault("effective_from", timezone.now())
    return ConsentDefinition.objects.create(**extra)


def test_definition_hash_is_computed_from_the_body() -> None:
    definition = make_definition(content_hash="0" * 64)
    assert definition.content_hash == consent_content_hash("Texto de prueba.")

    definition.body = "Otro texto."
    definition.save(update_fields=["body"])
    definition.refresh_from_db()
    assert definition.content_hash == consent_content_hash("Otro texto.")


def test_definition_versions_are_unique_per_code() -> None:
    make_definition()
    make_definition(version=2)
    make_definition(code="OTHER_CONSENT")
    assert_violates("uq_consent_definitions_version", lambda: make_definition())


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"version": 0}, "ck_consent_definitions_version"),
        (
            {"retired_at": timezone.now() - timedelta(days=30)},
            "ck_consent_definitions_dates",
        ),
    ],
)
def test_definition_values_must_be_valid(values: dict[str, Any], constraint: str) -> None:
    assert_violates(constraint, lambda: make_definition(**values))


# --- consent_records --------------------------------------------------------------------


def make_record(definition: ConsentDefinition, **extra: Any) -> ConsentRecord:
    extra.setdefault("action", ConsentAction.ACCEPTED)
    return ConsentRecord.objects.create(consent_definition=definition, **extra)


def test_a_record_belongs_to_a_buyer_or_to_a_user(
    buyer: Client,
    advisor_user: User,
    application: CreditApplication,
    make_session: Callable[..., BuyerSession],
) -> None:
    definition = make_definition()
    by_buyer = make_record(
        definition, client=buyer, application=application, buyer_session=make_session()
    )
    by_user = make_record(definition, user=advisor_user)

    assert by_buyer.user is None
    assert by_user.client is None


@pytest.mark.parametrize("actors", ["none", "both"])
def test_a_record_needs_exactly_one_actor(actors: str, buyer: Client, advisor_user: User) -> None:
    definition = make_definition()
    values = {"client": buyer, "user": advisor_user} if actors == "both" else {}
    assert_violates("ck_consent_records_actor", lambda: make_record(definition, **values))


def test_record_action_must_be_known(buyer: Client) -> None:
    definition = make_definition()
    assert_violates(
        "ck_consent_records_action",
        lambda: make_record(definition, client=buyer, action="POSTPONED"),
    )


def test_a_buyer_session_record_must_name_the_client(
    advisor_user: User, make_session: Callable[..., BuyerSession]
) -> None:
    definition = make_definition()
    assert_violates(
        "ck_consent_records_buyer_session",
        lambda: make_record(definition, user=advisor_user, buyer_session=make_session()),
    )


def test_an_accepted_definition_cannot_be_deleted(buyer: Client) -> None:
    definition = make_definition()
    make_record(definition, client=buyer)
    with pytest.raises(RestrictedError):
        definition.delete()


# --- application_status_history.actor_buyer_session ------------------------------------


def make_history(application: CreditApplication, **extra: Any) -> ApplicationStatusHistory:
    return ApplicationStatusHistory.objects.create(
        application=application,
        from_status=ApplicationStatus.DRAFT,
        to_status=ApplicationStatus.WITHDRAWN,
        application_version=2,
        **extra,
    )


def test_a_status_change_can_be_made_by_the_buyer(
    application: CreditApplication, make_session: Callable[..., BuyerSession]
) -> None:
    session = make_session()
    entry = make_history(application, actor_buyer_session=session)

    assert entry.actor_user is None
    assert entry.actor_buyer_session == session


def test_a_status_change_has_at_most_one_actor(
    application: CreditApplication,
    advisor_user: User,
    make_session: Callable[..., BuyerSession],
) -> None:
    session = make_session()
    assert_violates(
        "ck_application_status_actor",
        lambda: make_history(application, actor_user=advisor_user, actor_buyer_session=session),
    )


def test_deleting_a_session_keeps_the_history_and_the_consents(
    application: CreditApplication, buyer: Client, make_session: Callable[..., BuyerSession]
) -> None:
    session = make_session()
    entry = make_history(application, actor_buyer_session=session)
    record = make_record(make_definition(), client=buyer, buyer_session=session)

    session.delete()
    entry.refresh_from_db()
    record.refresh_from_db()

    assert entry.actor_buyer_session is None
    assert record.buyer_session is None
