import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.routes import router
from api.p2p_routes import p2p_router
from db.cassandra import db
from storage.ipfs_client import ipfs
from node.state import state_trie
from node.node_service import node_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.connect()
    await ipfs.connect()
    await node_service.start()
    yield
    # Shutdown
    await node_service.stop()
    await db.close()
    await ipfs.close()
    state_trie.close()


app = FastAPI(
    title="NodeManager",
    description="Блокчейн нода",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            
    allow_credentials=True,           
    allow_methods=["*"],              
    allow_headers=["*"],              
)

# Static files (frontend)
frontend_path = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# API routes
app.include_router(router, prefix="/api/v1")
app.include_router(p2p_router, prefix="/api/v1")


@app.get("/")
async def serve_frontend():
    from fastapi.responses import HTMLResponse
    html = (frontend_path / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)