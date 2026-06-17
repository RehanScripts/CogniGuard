"""Idempotent Kafka topic creation (Architecture §4.2).

Creates the 4 input + 2 output topics. Invoked on gateway startup and runnable
standalone:  python -m scripts.create_topics
"""

import logging

from confluent_kafka.admin import AdminClient, NewTopic

from app.config import settings
from app.schemas.topics import ALL_TOPICS

logger = logging.getLogger("cogniguard.create_topics")

NUM_PARTITIONS = 3  # dev; partition for throughput in prod (NFR-2)
REPLICATION_FACTOR = 1  # dev single-broker


def create_topics(
    num_partitions: int = NUM_PARTITIONS, replication_factor: int = REPLICATION_FACTOR
) -> list[str]:
    """Create any missing topics. Returns the list of newly-created topic names."""
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap})
    existing = set(admin.list_topics(timeout=10).topics.keys())
    to_create = [
        NewTopic(t, num_partitions=num_partitions, replication_factor=replication_factor)
        for t in ALL_TOPICS
        if t not in existing
    ]
    if not to_create:
        logger.info("all %d topics already exist", len(ALL_TOPICS))
        return []

    created: list[str] = []
    for topic, future in admin.create_topics(to_create).items():
        try:
            future.result()
            created.append(topic)
            logger.info("created topic %s", topic)
        except Exception as exc:  # already-exists or transient — idempotent
            logger.warning("skip topic %s: %s", topic, exc)
    return created


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    new = create_topics()
    print(f"created: {new or 'none (all present)'}")
