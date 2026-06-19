"""Benchmark question generation from user stories."""

from __future__ import annotations


def benchmark_questions_from_stories(stories: list[str]) -> list[str]:
    return [f"What answer should satisfy this story? {story}" for story in stories]
