"""Caché y Celery según el modo local (config/runtime_services.py)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.runtime_services import (
    MEMORY_BROKER,
    cache_settings,
    celery_broker_url,
    celery_result_backend,
)


def test_redis_cache_is_the_default_mode() -> None:
    config = cache_settings("redis", "redis://redis:6379/1")["default"]

    assert config["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert config["LOCATION"] == "redis://redis:6379/1"
    assert (config["KEY_PREFIX"], config["TIMEOUT"]) == ("mvp_credit", 300)


def test_database_cache_does_not_use_redis() -> None:
    config = cache_settings("database", "redis://redis:6379/1")["default"]

    assert config["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    assert config["LOCATION"] == "django_cache"
    assert (config["KEY_PREFIX"], config["TIMEOUT"]) == ("mvp_credit", 300)


def test_unknown_cache_backend_is_rejected() -> None:
    with pytest.raises(ImproperlyConfigured, match="CACHE_BACKEND"):
        cache_settings("memcached", "")


def test_the_worker_mode_uses_redis() -> None:
    url = "redis://redis:6379/0"

    assert celery_broker_url(url, always_eager=False) == url
    assert celery_result_backend(url, always_eager=False) == url


def test_inline_tasks_never_touch_redis() -> None:
    # Aunque haya REDIS_URL: en modo inmediato Celery igual pide un productor al broker.
    for url in ("redis://redis:6379/0", ""):
        assert celery_broker_url(url, always_eager=True) == MEMORY_BROKER
        assert celery_result_backend(url, always_eager=True) is None


def test_without_redis_tasks_must_run_inline() -> None:
    with pytest.raises(ImproperlyConfigured, match="CELERY_TASK_ALWAYS_EAGER"):
        celery_broker_url("", always_eager=False)
