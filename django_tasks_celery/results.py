"""Map Celery result metadata to Django TaskResult objects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from celery.states import FAILURE, PENDING, RECEIVED, REJECTED, RETRY, REVOKED, STARTED, SUCCESS

from django_tasks_celery.compat import Task, TaskError, TaskResult, TaskResultStatus

# Celery state → Django TaskResultStatus
_STATE_MAP: dict[str, TaskResultStatus] = {
    PENDING: TaskResultStatus.READY,
    RECEIVED: TaskResultStatus.READY,
    STARTED: TaskResultStatus.RUNNING,
    SUCCESS: TaskResultStatus.SUCCESSFUL,
    FAILURE: TaskResultStatus.FAILED,
    REVOKED: TaskResultStatus.FAILED,
    REJECTED: TaskResultStatus.FAILED,
    RETRY: TaskResultStatus.READY,
    "IGNORED": TaskResultStatus.FAILED,
}


def map_celery_state(state: str) -> TaskResultStatus:
    """Map a Celery state string to a Django TaskResultStatus."""
    return _STATE_MAP.get(state, TaskResultStatus.READY)


def meta_to_task_result(
    result_id: str,
    meta: dict[str, Any],
    task: Task[..., Any] | None = None,
    backend_alias: str = "default",
) -> TaskResult[Any]:
    """Convert Celery task metadata to a Django TaskResult."""
    status = map_celery_state(meta.get("status", PENDING))

    errors: list[TaskError] = []
    if status == TaskResultStatus.FAILED and meta.get("result"):
        exc = meta["result"]
        if isinstance(exc, BaseException):
            errors = [
                TaskError(
                    exception_class_path=f"{type(exc).__module__}.{type(exc).__qualname__}",
                    traceback=meta.get("traceback", ""),
                ),
            ]

    # Extract timestamps from Celery's extended result metadata
    date_done = meta.get("date_done")
    finished_at = None
    if date_done and status in (TaskResultStatus.SUCCESSFUL, TaskResultStatus.FAILED):
        if isinstance(date_done, str):
            try:
                finished_at = datetime.fromisoformat(date_done).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                pass
        elif isinstance(date_done, datetime):
            finished_at = date_done if date_done.tzinfo else date_done.replace(tzinfo=UTC)

    result = TaskResult(
        task=task,
        id=result_id,
        status=status,
        enqueued_at=None,
        started_at=None,
        finished_at=finished_at,
        last_attempted_at=None,
        args=[],
        kwargs={},
        backend=backend_alias,
        errors=errors,
        worker_ids=[],
    )

    # _return_value is init=False on the frozen dataclass, so we must use
    # object.__setattr__ to set it after construction.
    if status == TaskResultStatus.SUCCESSFUL and "result" in meta:
        object.__setattr__(result, "_return_value", meta["result"])

    return result
