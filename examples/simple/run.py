"""Script to enqueue example tasks and check results."""

import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
django.setup()

from django.tasks import default_task_backend
from tasks import add, greet, multiply

if __name__ == "__main__":
    print("Enqueuing tasks...")

    r1 = add.enqueue(3, 4)
    print(f"  add(3, 4) → result_id={r1.id}, status={r1.status}")

    r2 = multiply.enqueue(5, 6)
    print(f"  multiply(5, 6) → result_id={r2.id}, status={r2.status}")

    r3 = greet.enqueue("World")
    print(f"  greet('World') → result_id={r3.id}, status={r3.status}")

    print("\nWaiting for results...")
    time.sleep(2)

    for label, result in [("add", r1), ("multiply", r2), ("greet", r3)]:
        refreshed = default_task_backend.get_result(result.id)
        print(f"  {label}: status={refreshed.status}", end="")
        if refreshed.is_finished:
            print(f", return_value={refreshed.return_value}")
        else:
            print()
