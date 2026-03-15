"""Tests for priority mapping."""

from __future__ import annotations

import pytest

from django_tasks_celery.backend import map_priority


class TestMapPriority:
    @pytest.mark.parametrize(
        ("django_priority", "expected_celery"),
        [
            (-100, 0),
            (0, 128),  # middle: (0+100)*255/200 = 127.5 → rounds to 128
            (100, 255),
            (-50, 64),  # (-50+100)*255/200 = 63.75 → 64
            (50, 191),  # (50+100)*255/200 = 191.25 → 191
        ],
    )
    def test_priority_mapping(self, django_priority, expected_celery):
        result = map_priority(django_priority)
        assert result == expected_celery

    def test_priority_boundaries(self):
        assert map_priority(-100) == 0
        assert map_priority(100) == 255

    def test_default_priority_zero(self):
        # Priority 0 maps to middle of range
        result = map_priority(0)
        assert 127 <= result <= 128
