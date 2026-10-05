from typing import AsyncIterator, Optional

from bson import ObjectId
from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile

from core.database import get_db

BUCKET_NAME = "screenshots"


def _bucket() -> AsyncGridFSBucket:
    return AsyncGridFSBucket(get_db(), bucket_name=BUCKET_NAME)


async def save(run_id: ObjectId, item_id: Optional[ObjectId], step: str, content: bytes) -> ObjectId:
    """item_id is None for run-level failures such as a failed Weave login."""
    item_part = f"_item_{item_id}" if item_id else ""
    return await _bucket().upload_from_stream(
        f"run_{run_id}{item_part}_{step}.png",
        content,
        metadata={"run_id": run_id, "item_id": item_id, "content_type": "image/png"},
    )


async def open_for_run(run_id: ObjectId, screenshot_id: ObjectId) -> Optional[AsyncIterator[bytes]]:
    try:
        stream = await _bucket().open_download_stream(screenshot_id)
    except NoFile:
        return None
    if (stream.metadata or {}).get("run_id") != run_id:
        return None

    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await stream.readchunk():
            yield chunk

    return chunks()
