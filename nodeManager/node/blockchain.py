import asyncio
import hashlib
import json
import time
import uuid
from typing import Optional

from config import settings
from models.schemas import (
    Block, BlockHeader, Transaction, MiningTask, SubmitBlockRequest, TxStatus
)
from node.mempool import mempool
from node.state import state_trie
from db.cassandra import db
from node.p2p_client import p2p_client


class Blockchain:
    """Основная логика блокчейна."""

    def __init__(self):
        self._current_task_id: Optional[str] = None
        self._current_txs: list[Transaction] = []

    async def create_mining_task(self) -> MiningTask:
        """Создать задачу для майнера из транзакций в mempool."""

        # Определяем следующую высоту и пытаемся заблокировать
        last_block = await db.get_last_block()
        next_height = (last_block.height + 1) if last_block else 0

        from node.node_service import node_service
        locked = await db.acquire_mining_lock(next_height, node_service.node_id)
        if not locked:
            # Высота уже заблокирована другой нодой
            prev_hash = last_block.hash if last_block else "0" * 64
            self._current_task_id = None
            self._current_txs = []
            return MiningTask(
                task_id="locked",
                previous_hash=prev_hash,
                merkle_root="0" * 64,
                transactions=[],
                difficulty=settings.MINING_DIFFICULTY,
                timestamp=int(time.time()),
                reward_address=settings.BLOCK_REWARD_ADDRESS,
            )

        # Ждём транзакции если пусто (long-poll)
        if await mempool.count_pending() == 0:
            await mempool.wait_for_tasks(timeout=5.0)

        txs = await mempool.get_pending(limit=settings.MAX_TX_PER_BLOCK)

        if not txs:
            prev_hash = last_block.hash if last_block else "0" * 64
            self._current_task_id = None
            self._current_txs = []
            await db.release_mining_lock(next_height)
            return MiningTask(
                task_id="empty",
                previous_hash=prev_hash,
                merkle_root="0" * 64,
                transactions=[],
                difficulty=settings.MINING_DIFFICULTY,
                timestamp=int(time.time()),
                reward_address=settings.BLOCK_REWARD_ADDRESS,
            )

        last_block = await db.get_last_block()
        prev_hash = last_block.hash if last_block else "0" * 64

        # Вычисляем merkle root сразу — он нужен майнеру для PoW
        merkle_root = self._compute_merkle_root(txs)

        task_id = str(uuid.uuid4())
        self._current_task_id = task_id
        self._current_txs = txs

        return MiningTask(
            task_id=task_id,
            previous_hash=prev_hash,
            merkle_root=merkle_root,
            transactions=txs,
            difficulty=settings.MINING_DIFFICULTY,
            timestamp=int(time.time()),
            reward_address=settings.BLOCK_REWARD_ADDRESS,
        )

    async def submit_block(self, req: SubmitBlockRequest) -> tuple[bool, str]:
        """
        Принять блок от майнера.
        Возвращает (успех, сообщение).
        """
        if req.task_id != self._current_task_id:
            return False, f"Unknown or expired task: {req.task_id}"

        txs = self._current_txs
        if not txs:
            return False, "No transactions for this task"

        last_block = await db.get_last_block()
        prev_hash = last_block.hash if last_block else "0" * 64
        height = (last_block.height + 1) if last_block else 0

        # Вычисляем merkle root
        merkle_root = self._compute_merkle_root(txs)

        # Проверяем PoW БЕЗ state_root (как майнер считал)
        pow_hash = self._compute_pow_hash(
            prev_hash, merkle_root, req.timestamp,
            settings.MINING_DIFFICULTY, req.nonce, req.miner_address
        )
        if not pow_hash.startswith("0" * settings.MINING_DIFFICULTY):
            # Возвращаем транзакции обратно в pending
            await mempool.fail_transactions({t.hash for t in txs})
            self._current_task_id = None
            self._current_txs = []
            await db.release_mining_lock(height)
            return False, "PoW verification failed"

        # PoW пройден — применяем транзакции к состоянию
        bad_tx_hashes = set()
        for i, tx in enumerate(txs):
            if not state_trie.apply_transaction(tx):
                # Nonce не совпал — удаляем эту транзакцию из mempool навсегда
                bad_tx_hashes.add(tx.hash)
                # Откатываем уже применённые до этой
                for t in txs[:i]:
                    state_trie.revert_transaction(t)
                # Остальные (включая необработанные после failed) возвращаем в PENDING
                remaining = {t.hash for t in txs[:i] + txs[i+1:]}
                await mempool.fail_transactions(remaining)
                await mempool.remove_transactions(bad_tx_hashes)
                self._current_task_id = None
                self._current_txs = []
                await db.release_mining_lock(height)
                return False, f"Bad nonce in tx {tx.hash} — removed from mempool"

        state_root = state_trie.get_state_root()

        header = BlockHeader(
            previous_hash=prev_hash,
            merkle_root=merkle_root,
            timestamp=req.timestamp,
            difficulty=settings.MINING_DIFFICULTY,
            nonce=req.nonce,
            miner_address=req.miner_address,
            state_root=state_root,
        )

        block = Block(
            hash=self._compute_block_hash(header),
            header=header,
            transactions=txs,
            height=height,
        )

        # Сохраняем в Cassandra
        await db.save_block(block)
        await db.save_transactions(txs, height)

        # Удаляем из mempool
        await mempool.remove_confirmed({t.hash for t in txs})

        # Очищаем текущую задачу
        self._current_task_id = None
        self._current_txs = []

        # Снимаем блокировку и бродкастим всем пирам
        await db.release_mining_lock(height)
        asyncio.create_task(p2p_client.broadcast_block(height, block.hash))

        return True, block.hash

    def _compute_merkle_root(self, txs: list[Transaction]) -> str:
        if not txs:
            return "0" * 64

        hashes = [bytes.fromhex(tx.hash) for tx in txs]
        while len(hashes) > 1:
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])
            new_hashes = []
            for i in range(0, len(hashes), 2):
                new_hashes.append(
                    hashlib.sha256(hashes[i] + hashes[i + 1]).digest()
                )
            hashes = new_hashes
        return hashes[0].hex()

    def _compute_pow_hash(self, previous_hash: str, merkle_root: str,
                          timestamp: int, difficulty: int,
                          nonce: int, miner_address: str) -> str:
        """Хеш для PoW — без state_root (майнер не знает его заранее)."""
        raw = (
            f"{previous_hash}{merkle_root}{timestamp}"
            f"{difficulty}{nonce}{miner_address}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _compute_block_hash(self, header: BlockHeader) -> str:
        raw = (
            f"{header.previous_hash}{header.merkle_root}{header.timestamp}"
            f"{header.difficulty}{header.nonce}{header.miner_address}{header.state_root}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()


# singleton
blockchain = Blockchain()