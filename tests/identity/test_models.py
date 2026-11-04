from collections.abc import Callable
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity.models import AuthSession, PasswordResetToken, Role, User

pytestmark = pytest.mark.django_db


def test_internal_roles_are_seeded() -> None:
    assert set(Role.objects.values_list("code", flat=True)) == {
        "ADMIN",
        "ADVISOR",
        "INDEPENDENT_BROKER",
        "CONSTRUCTION_PARTNER",
    }


def test_email_is_normalized_to_lowercase() -> None:
    user = User.objects.create_user(email="  Andrea@Example.COM ", password="x")
    assert user.email == "andrea@example.com"

    user.email = "OTRO@EXAMPLE.COM"
    user.save()
    user.refresh_from_db()
    assert user.email == "otro@example.com"


def test_email_is_unique_regardless_of_case() -> None:
    User.objects.create_user(email="andrea@example.com", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        # `update` evita la normalización de `save()` y prueba el índice de la base.
        other = User.objects.create_user(email="otra@example.com", password="x")
        User.objects.filter(pk=other.pk).update(email="ANDREA@example.com")


def test_user_timestamps_are_set() -> None:
    user = User.objects.create_user(email="andrea@example.com", password="x")
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.deleted_at is None


def test_auth_session_expiry_must_be_after_creation(make_user: Callable[..., User]) -> None:
    user = make_user()
    with pytest.raises(IntegrityError), transaction.atomic():
        AuthSession.objects.create(
            user=user,
            refresh_token_hash="a" * 64,
            expires_at=timezone.now() - timedelta(minutes=1),
        )


def test_password_reset_expiry_must_be_after_creation(make_user: Callable[..., User]) -> None:
    user = make_user()
    with pytest.raises(IntegrityError), transaction.atomic():
        PasswordResetToken.objects.create(
            user=user,
            token_hash="b" * 64,
            expires_at=timezone.now() - timedelta(minutes=1),
        )


def test_a_session_can_only_be_rotated_once(make_user: Callable[..., User]) -> None:
    user = make_user()
    expires_at = timezone.now() + timedelta(hours=1)
    parent = AuthSession.objects.create(
        user=user, refresh_token_hash="c" * 64, expires_at=expires_at
    )
    AuthSession.objects.create(
        user=user, refresh_token_hash="d" * 64, expires_at=expires_at, rotated_from=parent
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AuthSession.objects.create(
            user=user, refresh_token_hash="e" * 64, expires_at=expires_at, rotated_from=parent
        )
