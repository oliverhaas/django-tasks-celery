# Quickstart

## 1. Configure Django settings

```python
# settings.py

# Celery
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
CELERY_RESULT_EXTENDED = True  # Required for get_result() to resolve task references

# Django Tasks
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default"],
    },
}
```

## 2. Create your Celery app

```python
# myproject/celery.py
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
```

## 3. Define tasks

```python
# myapp/tasks.py
from django.tasks import task

@task
def send_email(to: str, subject: str, body: str) -> str:
    # ... send the email ...
    return f"Sent to {to}"

@task(priority=10, queue_name="default")
def process_payment(order_id: int) -> dict:
    # ... process payment ...
    return {"order_id": order_id, "status": "completed"}
```

## 4. Enqueue tasks

```python
from myapp.tasks import send_email

# Fire and forget
result = send_email.enqueue(to="user@example.com", subject="Hello", body="World")
print(result.id)      # UUID
print(result.status)  # TaskResultStatus.READY

# Retrieve result later (requires CELERY_RESULT_EXTENDED = True)
from django.tasks import default_task_backend

task_result = default_task_backend.get_result(result.id)
if task_result.is_finished:
    print(task_result.return_value)
```

## 5. Start the worker

```bash
celery -A myproject.celery worker --loglevel=info
```

## Deferred execution

```python
from datetime import datetime, timedelta, UTC

# Run 5 minutes from now
result = send_email.using(run_after=datetime.now(UTC) + timedelta(minutes=5)).enqueue(
    to="user@example.com", subject="Reminder", body="Don't forget!"
)
```

## Known limitations

- **Priority mapping is broker-dependent.** Django priority (-100 to 100) maps to Celery/AMQP priority (0 to 255). This works correctly for RabbitMQ (higher number = higher priority) but is inverted for Redis (lower number = higher priority).
- **`get_result()` cannot distinguish pending from nonexistent tasks.** Celery returns `PENDING` for unknown task IDs. This is a fundamental Celery limitation.
