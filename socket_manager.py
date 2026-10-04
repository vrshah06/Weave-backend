import socketio
import asyncio
import json
from datetime import datetime

from config import CORS_ORIGINS

# We use an async server for FastAPI
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*' if CORS_ORIGINS == ['*'] else CORS_ORIGINS)

# Global list of active queues for SSE clients
sse_queues = []

@sio.on("connect")
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.on("disconnect")
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.on("join_workspace")
async def join_workspace(sid, workspaceId):
    room = f"ws_{workspaceId}"
    sio.enter_room(sid, room)
    print(f"Client {sid} joined room {room}")

async def emit_workspace_event(workspace_id, event_type, data):
    payload = {**data, "timestamp": datetime.utcnow().isoformat()}
    
    # 1. Emit to Socket.IO
    room = f"ws_{workspace_id}" if workspace_id else "ws_default"
    await sio.emit(event_type, payload, room=room)
    await sio.emit(event_type, payload)
    
    # 2. Push to SSE queues
    sse_payload = json.dumps({"type": event_type, **payload})
    for q in sse_queues:
        try:
            await q.put(f"data: {sse_payload}\n\n")
        except asyncio.QueueFull:
            pass
