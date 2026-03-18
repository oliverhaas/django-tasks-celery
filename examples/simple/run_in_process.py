"""Run example tasks with an in-process Celery worker (no external Redis needed)."""

import os
import sys

# Django setup
os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
sys.path.insert(0, os.path.dirname(__file__))

import django

django.setup()

from celery_app import app  # noqa: E402
from tasks import add, failing_example, greet, multiply  # noqa: E402

from django_tasks_celery.backend import CeleryBackend  # noqa: E402
from django_tasks_celery.register import ensure_celery_task  # noqa: E402

# Configure for eager mode (in-process execution, no broker needed)
app.conf.update(
    task_always_eager=True,
    task_eager_propagates=False,
    task_store_eager_result=True,
    result_extended=True,
    broker_url="memory://",
    result_backend="cache+memory://",
)

# Create backend and register tasks
backend = CeleryBackend(
    alias="default",
    params={"QUEUES": ["default"], "OPTIONS": {"CELERY_APP": "celery_app.app"}},
)
for t in [add, multiply, greet, failing_example]:
    ensure_celery_task(t, app, backend)

if __name__ == "__main__":
    print("=" * 60)
    print("django-tasks-celery example (in-process eager mode)")
    print("=" * 60)

    # --- Successful tasks ---
    print("\n1. add(3, 4)")
    r1 = backend.enqueue(add, args=(3, 4), kwargs={})
    print(f"   enqueued: id={r1.id}, status={r1.status}")
    r1_result = backend.get_result(r1.id)
    print(f"   result:   status={r1_result.status}, return_value={r1_result.return_value}")

    print("\n2. multiply(5, 6)")
    r2 = backend.enqueue(multiply, args=(5, 6), kwargs={})
    print(f"   enqueued: id={r2.id}, status={r2.status}")
    r2_result = backend.get_result(r2.id)
    print(f"   result:   status={r2_result.status}, return_value={r2_result.return_value}")

    print("\n3. greet('World')")
    r3 = backend.enqueue(greet, args=("World",), kwargs={})
    print(f"   enqueued: id={r3.id}, status={r3.status}")
    r3_result = backend.get_result(r3.id)
    print(f"   result:   status={r3_result.status}, return_value={r3_result.return_value}")

    # --- Failing task ---
    print("\n4. failing_example() — expected to fail")
    r4 = backend.enqueue(failing_example, args=(), kwargs={})
    print(f"   enqueued: id={r4.id}, status={r4.status}")
    r4_result = backend.get_result(r4.id)
    print(f"   result:   status={r4_result.status}")
    if r4_result.errors:
        print(f"   error:    {r4_result.errors[0].exception_class_path}")

    # --- Task reference in get_result ---
    print("\n5. Verify task reference survives get_result()")
    print(f"   r1_result.task is add: {r1_result.task is add}")
    print(f"   r1_result.task.name:   {r1_result.task.name}")

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
