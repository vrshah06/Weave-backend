from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import socketio
import os
import sys

if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

from routers import router
from database import get_db
from socket_manager import sio

app = FastAPI(title="Weave Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Wrap FastAPI with Socket.IO ASGI app
sio_app = socketio.ASGIApp(socketio_server=sio, other_asgi_app=app)

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_path, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        
        # Try to serve exact file first (e.g. vite.svg, favicon.ico)
        file_path = os.path.join(frontend_dist_path, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # Fallback to index.html for SPA routing
        return FileResponse(os.path.join(frontend_dist_path, "index.html"))

@app.on_event("startup")
async def startup_db_client():
    get_db()
    print("MongoDB connection initialized")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"==================================================")
    print(f"WEAVE AUTOMATION BACKEND SERVER RUNNING ON {port}")
    print(f"==================================================")
    uvicorn.run("app:sio_app", host=host, port=port, reload=True)
