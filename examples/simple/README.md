# Simple Example

Minimal example of django-tasks-celery with Redis as broker.

## Prerequisites

- Redis running on localhost:6379
- Python 3.12+

## Setup

```bash
pip install django-tasks-celery redis
```

## Run

Start a Celery worker:

```bash
DJANGO_SETTINGS_MODULE=settings celery -A celery_app worker --loglevel=info
```

In another terminal, enqueue tasks:

```bash
DJANGO_SETTINGS_MODULE=settings python run.py
```
