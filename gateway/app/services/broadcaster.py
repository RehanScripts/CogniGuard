"""SOC broadcaster (Architecture §4.1/§6, Implementation.md Phase 9): bridges the
`risk_scores`/`decisions` Kafka output topics to a Redis pub/sub channel (`soc-feed`)
so `routers/ws.py` can fan them out to connected dashboard WebSocket clients.

Runs as a background thread, not an asyncio task -- `confluent_kafka.Consumer.poll()`
is blocking C code (same reasoning as `kafka_client.py`'s sync producer/consumer).
"""

from __future__ import annotations

import logging
import threading
import uuid

from confluent_kafka import Consumer

from ..config import settings
from ..redis_client import redis_client
from ..schemas.topics import T_DECISIONS, T_RISK_SCORES

logger = logging.getLogger("cogniguard.gateway.broadcaster")

SOC_FEED_CHANNEL = "soc-feed"


def run(stop_event: threading.Event) -> None:
    # A live fan-out feed, not a stateful consumer: each broadcaster instance gets its
    # own ephemeral consumer group reading from "latest" (no backlog replay, and no
    # rebalance contention with a previous instance's group membership -- this matters
    # in dev, where uvicorn --reload restarts the app, and in tests, where every
    # `TestClient(app)` context starts/stops the lifespan).
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": f"soc-broadcaster-{uuid.uuid4().hex}",
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([T_RISK_SCORES, T_DECISIONS])
    try:
        while not stop_event.is_set():
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                redis_client.publish(SOC_FEED_CHANNEL, msg.value())
            except Exception:
                logger.exception("soc-feed publish failed")
    finally:
        consumer.close()


def start() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(target=run, args=(stop_event,), daemon=True, name="soc-broadcaster")
    thread.start()
    return thread, stop_event
