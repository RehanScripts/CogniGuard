"""SOC WebSocket feed (Implementation.md Phase 9): streams the `soc-feed` Redis
pub/sub channel `services/broadcaster.py` publishes to. Uses `redis.asyncio` (not the
sync `redis_client`) so a slow/idle dashboard connection never blocks the event loop
for other connected clients.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..redis_client import async_redis_client
from ..services.broadcaster import SOC_FEED_CHANNEL

router = APIRouter()


@router.websocket("/soc-feed")
async def soc_feed(websocket: WebSocket) -> None:
    await websocket.accept()
    pubsub = async_redis_client.pubsub()
    await pubsub.subscribe(SOC_FEED_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(SOC_FEED_CHANNEL)
        await pubsub.aclose()
