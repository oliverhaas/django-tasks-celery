"""CeleryBackend — Celery backend for Django's task framework."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from asgiref.sync import sync_to_async
from django.core import checks
from django.utils.module_loading import import_string

from django_tasks_celery.compat import (
    BaseTaskBackend,
    Task,
    TaskResult,
    TaskResultStatus,
    task_enqueued,
)
from django_tasks_celery.register import ensure_celery_task
from django_tasks_celery.results import meta_to_task_result

T = TypeVar("T")
P = ParamSpec("P")


def map_priority(django_priority: int) -> int:
    """Map Django priority (-100 to 100) to Celery/AMQP priority (0 to 255)."""
    return max(0, min(255, round((django_priority + 100) * 255 / 200)))


class CeleryBackend(BaseTaskBackend):
    supports_defer = True
    supports_async_task = True
    supports_priority = True

    @property
    def supports_get_result(self) -> bool:  # type: ignore[override]
        try:
            from celery.backends.base import DisabledBackend

            return not isinstance(self._get_celery_app().backend, DisabledBackend)
        except Exception:
            return False

    def _get_celery_app(self) -> Any:
        """Resolve the Celery app: from OPTIONS or auto-detect."""
        celery_app_path = self.options.get("celery_app")
        if celery_app_path:
            return import_string(celery_app_path)
        from celery import current_app

        return current_app._get_current_object()

    def _build_send_options(self, task: Task[..., Any]) -> dict[str, Any]:
        """Build options dict for Celery's send_task()."""
        options: dict[str, Any] = {}

        if task.queue_name != "default":
            options["queue"] = task.queue_name

        if task.priority != 0:
            options["priority"] = map_priority(task.priority)

        if task.run_after is not None:
            options["eta"] = task.run_after

        return options

    def enqueue(
        self,
        task: Task[P, T],
        args: Any,
        kwargs: Any,
    ) -> TaskResult[T]:
        self.validate_task(task)
        app = self._get_celery_app()
        ensure_celery_task(task, app, self)

        options = self._build_send_options(task)
        celery_task = app.tasks[task.module_path]
        celery_result = celery_task.apply_async(
            args=list(args),
            kwargs=dict(kwargs),
            **options,
        )

        task_result = TaskResult(
            task=task,
            id=celery_result.id,
            status=TaskResultStatus.READY,
            enqueued_at=datetime.now(UTC),
            started_at=None,
            finished_at=None,
            last_attempted_at=None,
            args=list(args),
            kwargs=dict(kwargs),
            backend=self.alias,
            errors=[],
            worker_ids=[],
        )
        task_enqueued.send(sender=type(self), task_result=task_result)
        return task_result

    async def aenqueue(
        self,
        task: Task[P, T],
        args: Any,
        kwargs: Any,
    ) -> TaskResult[T]:
        return await sync_to_async(self.enqueue, thread_sensitive=True)(task=task, args=args, kwargs=kwargs)

    def get_result(self, result_id: str) -> TaskResult[Any]:
        app = self._get_celery_app()
        meta = app.backend.get_task_meta(result_id)
        return meta_to_task_result(
            result_id=result_id,
            meta=meta,
            backend_alias=self.alias,
        )

    async def aget_result(self, result_id: str) -> TaskResult[Any]:
        return await sync_to_async(self.get_result, thread_sensitive=True)(
            result_id=result_id,
        )

    def check(self, **kwargs: Any) -> Iterable[checks.CheckMessage]:
        messages: list[checks.CheckMessage] = []

        try:
            import celery  # noqa: F401
        except ImportError:
            messages.append(
                checks.Error(
                    "celery is not installed.",
                    hint="Install celery: pip install celery",
                    id="django_tasks_celery.E001",
                ),
            )
            return messages

        try:
            self._get_celery_app()
        except Exception as e:
            messages.append(
                checks.Error(
                    f"Could not resolve Celery app: {e}",
                    hint="Set OPTIONS.celery_app or configure a default Celery app.",
                    id="django_tasks_celery.E002",
                ),
            )
            return messages

        if not self.supports_get_result:
            messages.append(
                checks.Warning(
                    "Celery result backend is disabled. get_result() will not work.",
                    hint="Set CELERY_RESULT_BACKEND in your Django settings.",
                    id="django_tasks_celery.W001",
                ),
            )

        return messages
