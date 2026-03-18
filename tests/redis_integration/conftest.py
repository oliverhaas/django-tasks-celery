"""Celery pytest plugin configuration for Redis integration tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.register import _django_task_registry, ensure_celery_task
from tests.tasks import async_task, context_task, failing_task, simple_task


@pytest.fixture(scope="session")
def redis_url():
    """Start a Redis container and return its URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer() as redis:
        yield f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def celery_config(redis_url):
    return {
        "broker_url": redis_url,
        "result_backend": redis_url,
        "task_always_eager": False,
        "task_eager_propagates": False,
        "result_extended": True,
    }


@pytest.fixture(scope="session")
def celery_worker_parameters():
    return {
        "perform_ping_check": False,
    }


@pytest.fixture
def backend():
    return CeleryBackend(
        alias="default",
        params={"QUEUES": ["default", "high", "low"]},
    )


@pytest.fixture(autouse=True)
def _patch_app_and_register(backend, celery_app):
    """Wire up the test celery_app and register tasks."""
    _django_task_registry.clear()
    for task in [simple_task, failing_task, async_task, context_task]:
        ensure_celery_task(task, celery_app, backend)
    with patch.object(backend, "_get_celery_app", return_value=celery_app):
        yield
    _django_task_registry.clear()
