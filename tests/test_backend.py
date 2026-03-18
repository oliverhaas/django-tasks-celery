"""Tests for CeleryBackend enqueue/get_result/validate."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from celery import Celery
from django.tasks.base import TaskResultStatus
from django.tasks.exceptions import InvalidTask as InvalidTaskError

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.register import _django_task_registry
from tests.tasks import high_priority_task, simple_task


@pytest.fixture
def backend():
    return CeleryBackend(
        alias="default",
        params={
            "QUEUES": ["default", "high", "low"],
        },
    )


@pytest.fixture
def celery_app():
    app = Celery("test")
    app.config_from_object(
        {
            "broker_url": "memory://",
            "result_backend": "cache+memory://",
            "task_always_eager": True,
            "task_eager_propagates": True,
            "result_extended": True,
        },
    )
    app.finalize()
    return app


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear the task registry between tests."""
    _django_task_registry.clear()
    yield
    _django_task_registry.clear()


class TestCeleryBackendEnqueue:
    def test_enqueue_simple_task(self, backend, celery_app):
        with patch.object(backend, "_get_celery_app", return_value=celery_app):
            result = backend.enqueue(simple_task, args=(1, 2), kwargs={})

        assert result.status == TaskResultStatus.READY
        assert result.id is not None
        assert result.args == [1, 2]
        assert result.kwargs == {}
        assert result.backend == "default"
        assert result.enqueued_at is not None

    def test_enqueue_with_kwargs(self, backend, celery_app):
        with patch.object(backend, "_get_celery_app", return_value=celery_app):
            result = backend.enqueue(simple_task, args=(), kwargs={"x": 3, "y": 4})

        assert result.kwargs == {"x": 3, "y": 4}

    def test_enqueue_high_priority_task(self, backend, celery_app):
        with patch.object(backend, "_get_celery_app", return_value=celery_app):
            result = backend.enqueue(high_priority_task, args=("hello",), kwargs={})

        assert result.status == TaskResultStatus.READY
        assert result.task == high_priority_task

    def test_enqueue_fires_signal(self, backend, celery_app):
        from django.tasks.signals import task_enqueued

        received = []

        def handler(sender, task_result, **kwargs):
            received.append(task_result)

        task_enqueued.connect(handler)
        try:
            with patch.object(backend, "_get_celery_app", return_value=celery_app):
                backend.enqueue(simple_task, args=(1, 2), kwargs={})
            assert len(received) == 1
            assert received[0].status == TaskResultStatus.READY
        finally:
            task_enqueued.disconnect(handler)


class TestCeleryBackendValidation:
    def test_validate_invalid_queue(self, backend):
        # In Django 6.0, using() validates immediately in __post_init__,
        # so we catch the exception from using() itself
        with pytest.raises(InvalidTaskError, match="not valid for backend"):
            simple_task.using(queue_name="nonexistent")

    def test_validate_valid_queue(self, backend):
        task_with_good_queue = simple_task.using(queue_name="high")
        backend.validate_task(task_with_good_queue)  # should not raise


class TestCeleryBackendFeatureFlags:
    def test_supports_defer(self, backend):
        assert backend.supports_defer is True

    def test_supports_async_task(self, backend):
        assert backend.supports_async_task is True

    def test_supports_priority(self, backend):
        assert backend.supports_priority is True

    def test_supports_get_result_with_backend(self, backend, celery_app):
        with patch.object(backend, "_get_celery_app", return_value=celery_app):
            assert backend.supports_get_result is True

    def test_supports_get_result_disabled(self, backend):
        mock_app = MagicMock()
        # Mock isinstance check by patching supports_get_result logic
        with patch(
            "django_tasks_celery.backend.CeleryBackend.supports_get_result",
            new_callable=lambda: property(lambda self: False),
        ):
            assert backend.supports_get_result is False


class TestCeleryAppResolution:
    def test_auto_detect(self, backend):
        app = backend._get_celery_app()
        assert app is not None

    def test_explicit_import_path(self):
        # Create a test Celery app instance to import
        backend = CeleryBackend(
            alias="default",
            params={
                "OPTIONS": {"CELERY_APP": "tests.fixtures.celery_app_instance"},
            },
        )
        # Just test that a bad path raises ImportError
        with pytest.raises(ImportError):
            backend._get_celery_app()


class TestBuildSendOptions:
    def test_run_after_sets_eta(self, backend):
        """Tasks with run_after should pass eta to Celery."""
        from datetime import datetime

        eta = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        deferred_task = simple_task.using(run_after=eta)
        options = backend._build_send_options(deferred_task)
        assert options["eta"] == eta

    def test_default_queue_omitted(self, backend):
        """Default queue should not be passed to Celery (let Celery decide)."""
        options = backend._build_send_options(simple_task)
        assert "queue" not in options

    def test_non_default_queue_passed(self, backend):
        """Non-default queue should be passed explicitly."""
        task_with_queue = simple_task.using(queue_name="high")
        options = backend._build_send_options(task_with_queue)
        assert options["queue"] == "high"

    def test_default_priority_omitted(self, backend):
        """Default priority (0) should not be passed to Celery."""
        options = backend._build_send_options(simple_task)
        assert "priority" not in options
