"""
Node Service — управление нодой.

Каждая нода:
1. При старте регистрирует себя в Cassandra (таблица `nodes`)
2. Переигрывает блоки из Cassandra → LevelDB (восстановление state)
3. При остановке помечает себя как неактивную

Блоки реплицируются через Cassandra gossip ring.
При уведомлении о новом блоке — переигрываем блоки.
"""

import asyncio
import json
import logging
import os
import uuid

from config import settings
from db.cassandra import db
from models.schemas import Transaction
from node.state import state_trie

logger = logging.getLogger(__name__)


class NodeService:
    def __init__(self):
        self.node_id: str = ""
        self.node_name: str = ""
        self.api_host: str = ""
        self.api_port: int = settings.PORT
        self._last_replayed_height: int = -1

    async def initialize(self):
        """Инициализация ноды — генерация ID, определение адреса, регистрация."""
        self.node_id = os.getenv("NODE_ID", f"node-{uuid.uuid4().hex[:12]}")
        self.node_name = os.getenv("NODE_NAME", self.node_id)
        self.api_host = os.getenv("NODE_HOST", "localhost")
        self.api_port = int(os.getenv("NODE_PORT", str(settings.PORT)))

        await db.register_node(
            node_id=self.node_id,
            name=self.node_name,
            api_host=self.api_host,
            api_port=self.api_port,
        )

        logger.info(
            f"Node initialized: {self.node_id} @ {self.api_host}:{self.api_port}"
        )

    async def _heartbeat_loop(self):
        """Фоновый цикл: обновляем last_seen в Cassandra каждые 30с."""
        while True:
            try:
                last_block = await db.get_last_block()
                height = last_block.height if last_block else 0
                await db.update_node_heartbeat(self.node_id, height)
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            await asyncio.sleep(30)

    async def start(self):
        """Старт ноды: инициализация + переигровка блоков + heartbeat."""
        await self.initialize()
        await self.replay_blocks()
        asyncio.create_task(self._heartbeat_loop())
        logger.info("Node started, state synced from blockchain")

    async def stop(self):
        """Остановка ноды."""
        await db.mark_node_inactive(self.node_id)
        logger.info(f"Node {self.node_id} stopped")

    async def replay_blocks(self):
        """
        Переиграть блоки из Cassandra для восстановления state.
        Пропускает уже переигранные блоки (по _last_replayed_height).
        Вызывается при старте и при получении уведомления о новом блоке.
        """
        try:
            last_block = await db.get_last_block()
            current_height = last_block.height if last_block else -1

            if current_height <= self._last_replayed_height:
                return

            from_height = self._last_replayed_height + 1
            blocks = await db.get_blocks_since(from_height=from_height, limit=10000)

            if not blocks:
                return

            count = 0
            for block_info in blocks:
                height = block_info["height"]
                tx_rows = await db.get_block_transactions(height)

                for row in tx_rows:
                    tx = Transaction(
                        hash=row.hash,
                        from_address=row.from_address,
                        to_address=row.to_address,
                        nonce=row.nonce,
                        payload=json.loads(row.payload) if isinstance(row.payload, str) else row.payload,
                        signature=row.signature,
                        timestamp=row.timestamp,
                    )
                    state_trie.apply_transaction(tx)
                    count += 1

                self._last_replayed_height = height

            if count > 0:
                logger.info(
                    f"Replayed {count} tx(s) from {len(blocks)} block(s) "
                    f"(up to height {self._last_replayed_height})"
                )

        except Exception as e:
            logger.error(f"Block replay failed: {e}")


# singleton
node_service = NodeService()
