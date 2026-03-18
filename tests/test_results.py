"""Tests for Celery result → Django TaskResult state mapping."""

from __future__ import annotations

from datetime import UTC

import pytest
from celery.states import FAILURE, PENDING, RECEIVED, RETRY, REVOKED, STARTED, SUCCESS
from django.tasks.base import TaskResultStatus

from django_tasks_celery.results import map_celery_state, meta_to_task_result


class TestMapCeleryState:
    @pytest.mark.parametrize(
        ("celery_state", "expected"),
        [
            (PENDING, TaskResultStatus.READY),
            (RECEIVED, TaskResultStatus.READY),
            (STARTED, TaskResultStatus.RUNNING),
            (SUCCESS, TaskResultStatus.SUCCESSFUL),
            (FAILURE, TaskResultStatus.FAILED),
            (REVOKED, TaskResultStatus.FAILED),
            ("REJECTED", TaskResultStatus.FAILED),
            (RETRY, TaskResultStatus.READY),
            ("IGNORED", TaskResultStatus.FAILED),
            ("UNKNOWN_STATE", TaskResultStatus.READY),
        ],
    )
    def test_state_mapping(self, celery_state, expected):
        assert map_celery_state(celery_state) == expected


class TestMetaToTaskResult:
    def test_pending_meta(self):
        meta = {"status": PENDING, "result": None}
        result = meta_to_task_result("abc-123", meta)
        assert result.id == "abc-123"
        assert result.status == TaskResultStatus.READY

    def test_success_meta(self):
        meta = {"status": SUCCESS, "result": 42, "date_done": "2025-01-01T12:00:00"}
        result = meta_to_task_result("abc-123", meta)
        assert result.status == TaskResultStatus.SUCCESSFUL
        assert result.finished_at is not None

    def test_failure_meta_with_exception(self):
        exc = ValueError("test error")
        meta = {"status": FAILURE, "result": exc, "traceback": "Traceback..."}
        result = meta_to_task_result("abc-123", meta)
        assert result.status == TaskResultStatus.FAILED
        assert len(result.errors) == 1
        assert "ValueError" in result.errors[0].exception_class_path

    def test_failure_meta_without_exception(self):
        meta = {"status": FAILURE, "result": None}
        result = meta_to_task_result("abc-123", meta)
        assert result.status == TaskResultStatus.FAILED
        assert len(result.errors) == 0

    def test_default_backend_alias(self):
        meta = {"status": PENDING, "result": None}
        result = meta_to_task_result("abc-123", meta)
        assert result.backend == "default"

    def test_custom_backend_alias(self):
        meta = {"status": PENDING, "result": None}
        result = meta_to_task_result("abc-123", meta, backend_alias="celery")
        assert result.backend == "celery"

    def test_success_meta_populates_return_value(self):
        """Successful result should have return_value accessible."""
        meta = {"status": SUCCESS, "result": 42}
        result = meta_to_task_result("abc-123", meta)
        assert result.return_value == 42

    def test_meta_populates_args_kwargs(self):
        """Extended metadata args/kwargs should be reflected in TaskResult."""
        meta = {"status": SUCCESS, "result": 42, "args": [1, 2], "kwargs": {"x": 3}}
        result = meta_to_task_result("abc-123", meta)
        assert result.args == [1, 2]
        assert result.kwargs == {"x": 3}

    def test_meta_populates_worker_ids(self):
        """Worker hostname from metadata should populate worker_ids."""
        meta = {"status": SUCCESS, "result": 42, "worker": "celery@myhost"}
        result = meta_to_task_result("abc-123", meta)
        assert result.worker_ids == ["celery@myhost"]

    def test_meta_without_worker(self):
        """Missing worker in metadata should leave worker_ids empty."""
        meta = {"status": SUCCESS, "result": 42}
        result = meta_to_task_result("abc-123", meta)
        assert result.worker_ids == []

    def test_failure_meta_with_string_exception(self):
        """Some result backends store exceptions as strings instead of objects."""
        meta = {"status": FAILURE, "result": "builtins.ValueError", "traceback": "Traceback..."}
        result = meta_to_task_result("abc-123", meta)
        assert result.status == TaskResultStatus.FAILED
        assert len(result.errors) == 1
        assert result.errors[0].exception_class_path == "builtins.ValueError"
        assert result.errors[0].traceback == "Traceback..."

    def test_failure_meta_with_datetime_object(self):
        """date_done can be a datetime object (not just a string)."""
        from datetime import datetime

        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        meta = {"status": FAILURE, "result": ValueError("err"), "date_done": dt}
        result = meta_to_task_result("abc-123", meta)
        assert result.finished_at == dt
