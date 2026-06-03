"""
P2P API — межнодовое взаимодействие.
"""

import logging
from fastapi import APIRouter

from db.cassandra import db
from node.state import state_trie
from models.schemas import Transaction

logger = logging.getLogger(__name__)

p2p_router = APIRouter()


@p2p_router.post("/p2p/block")
async def p2p_notify_block(data: dict):
    """
    Уведомление о новом блоке от другой ноды.
    После получения — переигрываем блоки из Cassandra.
    """
    height = data.get("height")
    block_hash = data.get("hash", "?")[:16]
    logger.info(f"p2p: notified about block #{height} hash={block_hash}")

    # Запускаем replay блоков из Cassandra
    from node.node_service import node_service
    await node_service.replay_blocks()

    return {"status": "ok"}


@p2p_router.get("/p2p/blocks")
async def p2p_get_blocks(from_height: int = 0, limit: int = 100):
    """Отдать блоки для синхронизации."""
    blocks = await db.get_blocks_since(from_height, limit)
    return {"blocks": blocks, "count": len(blocks)}