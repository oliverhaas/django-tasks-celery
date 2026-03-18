# django-tasks-celery

Celery backend for Django 6.0's built-in `django.tasks` framework. Implements `BaseTaskBackend` so that `@task` / `enqueue()` dispatches to Celery workers.

## Features

- Full `BaseTaskBackend` implementation: `enqueue`, `get_result`, system checks
- Priority mapping (Django -100..100 to Celery/AMQP 0..255)
- Deferred execution via Celery's `eta`
- Sync and async task function support
- Django signals: `task_enqueued`, `task_started`, `task_finished`
- Dynamic `supports_get_result` based on Celery result backend
- Worker-side task auto-discovery (no manual registration needed)

## Quick Start

```bash
pip install django-tasks-celery[celery]
```

```python
# settings.py
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
CELERY_RESULT_EXTENDED = True

TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default"],
    },
}
```

```python
from django.tasks import task

@task
def send_email(to, subject, body):
    ...

result = send_email.enqueue(to="user@example.com", subject="Hello", body="World")
```
