"""Example task definitions."""

from django.tasks import task


@task
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


@task(priority=10)
def multiply(x: int, y: int) -> int:
    """Multiply two numbers with higher priority."""
    return x * y


@task
def greet(name: str) -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"


@task
def failing_example() -> None:
    """A task that always fails (for testing error handling)."""
    msg = "This task is designed to fail"
    raise RuntimeError(msg)
