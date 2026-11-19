"""Minimal adapter contract. Feed health is exposed independently of records."""
from typing import Protocol
from .model import Item


class Source(Protocol):
    feeds: dict[str, str]

    def fetch(self) -> list[Item]: ...
