import json
from functools import lru_cache

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient

from .config import settings


@lru_cache(maxsize=1)
def get_producer() -> Producer:
    """Lazily-constructed shared Kafka producer (fire-and-forget, off the hot path)."""
    return Producer({"bootstrap.servers": settings.kafka_bootstrap, "linger.ms": 5})


def get_consumer(group_id: str, topics: list[str]) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe(topics)
    return consumer


def get_admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": settings.kafka_bootstrap})


def produce(topic: str, key: str, value: dict) -> None:
    """Enqueue an event. Non-blocking; never block the request hot path."""
    p = get_producer()
    p.produce(topic, key=key, value=json.dumps(value, default=str))
    p.poll(0)


def ping() -> bool:
    """Return True if a Kafka broker responds to a metadata request."""
    try:
        md = get_admin().list_topics(timeout=3)
        return md is not None
    except Exception:
        return False
