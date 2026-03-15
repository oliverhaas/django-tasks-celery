# django-tasks-celery

> **Exploratory / Alpha** — This package is an early-stage exploration of a Celery backend for Django's `django.tasks` framework. It is **not yet production-ready**. APIs may change without notice. Use at your own risk.

Celery backend for Django 6.0's built-in `django.tasks` framework. Implements `BaseTaskBackend` so that `@task` / `enqueue()` dispatches to Celery workers.

## Installation

```bash
pip install django-tasks-celery[celery]
```

Or with [celery-asyncio](https://github.com/oliverhaas/celery-asyncio) (same API, async-native rewrite):

```bash
pip install django-tasks-celery[celery-asyncio]
```

## Configuration

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

## Usage

```python
from django.tasks import task

@task
def send_email(to, subject, body):
    ...

# Enqueue
result = send_email.enqueue(to="user@example.com", subject="Hello", body="World")
```

## Compatibility

- **Django**: 6.0+
- **Celery**: 5.4+ (or celery-asyncio)
- **Python**: 3.12+
