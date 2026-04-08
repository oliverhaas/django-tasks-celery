# Simple Example

Minimal example of django-tasks-celery.

## Setup

```bash
uv sync
```

## Run (no Redis needed)

```bash
uv run python run_in_process.py
```

This uses Celery's eager mode to run everything in-process.

## Run with Redis

Start Redis on localhost:6379, then:

```bash
DJANGO_SETTINGS_MODULE=settings uv run celery -A celery_app worker --loglevel=info
```

In another terminal:

```bash
uv run python run.py
```
