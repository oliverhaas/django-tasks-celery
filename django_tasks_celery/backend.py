"""CeleryBackend — Celery backend for Django's task framework."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from django.core import checks
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import Task, TaskResult, TaskResultStatus
from django.tasks.signals import task_enqueued
from django.utils.module_loading import import_string

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
    def supports_get_result(self) -> bool:
        try:
            from celery.backends.base import DisabledBackend

            return not isinstance(self._get_celery_app().backend, DisabledBackend)
        except Exception:
            return False

    def _get_celery_app(self) -> Any:
        """Resolve the Celery app: from OPTIONS or auto-detect."""
        celery_app_path = self.options.get("CELERY_APP")
        if celery_app_path:
            return import_string(celery_app_path)
        from celery import current_app

        return current_app._get_current_object()

    def validate_task(self, task: Task[..., Any]) -> None:
        """Validate and register the task with Celery.

        This runs during Task.__post_init__ (at import time), ensuring tasks
        are registered with Celery in both web and worker processes — solving
        worker-side task discovery.
        """
        super().validate_task(task)
        try:
            app = self._get_celery_app()
            ensure_celery_task(task, app, self)
        except Exception:
            # Registration is best-effort at validate time.
            # It will succeed later at enqueue() time.
            pass

    def _build_send_options(self, task: Task[..., Any]) -> dict[str, Any]:
        """Build options dict for Celery's apply_async().

        When queue_name is "default" (Django's default), we omit it so Celery
        uses its own default routing. Non-default queues are passed explicitly.
        """
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

    def get_result(self, result_id: str) -> TaskResult[Any]:
        from django_tasks_celery.register import _django_task_registry

        app = self._get_celery_app()
        meta = app.backend.get_task_meta(result_id)

        # Look up the Django Task from our registry via the Celery task name
        # (requires CELERY_RESULT_EXTENDED = True for task_name in metadata)
        task_name = meta.get("task_name") or meta.get("name")
        task = _django_task_registry.get(task_name) if task_name else None

        return meta_to_task_result(
            result_id=result_id,
            meta=meta,
            task=task,
            backend_alias=self.alias,
        )

    def check(self, **kwargs: Any) -> Iterable[checks.CheckMessage]:
        messages: list[checks.CheckMessage] = []

        try:
            app = self._get_celery_app()
        except Exception as e:
            messages.append(
                checks.Error(
                    f"Could not resolve Celery app: {e}",
                    hint="Set OPTIONS.CELERY_APP or configure a default Celery app.",
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

        if not app.conf.get("result_extended", False):
            messages.append(
                checks.Warning(
                    "CELERY_RESULT_EXTENDED is not enabled. get_result() will not be able to resolve task references.",
                    hint="Set CELERY_RESULT_EXTENDED = True in your Django settings.",
                    id="django_tasks_celery.W002",
                ),
            )

        return messages
