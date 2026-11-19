"""Source-neutral records and UTC time helpers."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)


@dataclass
class Item:
    id: str
    source: str
    title: str
    url: str
    item_url: str
    image: str
    posted_at: str
    metrics: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
