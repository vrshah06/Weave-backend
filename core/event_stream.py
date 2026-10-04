import asyncio
import json
from datetime import datetime

_subscribers: list[asyncio.Queue] = []


def subscribe() -> asyncio.Queue:
    queue = asyncio.Queue()
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.remove(queue)


async def publish_event(event_type: str, data: dict) -> None:
    message = json.dumps({"type": event_type, **data, "timestamp": datetime.utcnow().isoformat()})
    for queue in _subscribers:
        queue.put_nowait(f"data: {message}\n\n")
