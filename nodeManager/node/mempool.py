import asyncio
from typing import Optional

from models.schemas import Transaction, TxStatus


class Mempool:
    """Пул неподтверждённых транзакций в памяти."""

    def __init__(self):
        self._transactions: dict[str, Transaction] = {}
        self._lock = asyncio.Lock()
        self._new_tx_event = asyncio.Event()

    async def add_transaction(self, tx: Transaction) -> bool:
        """Добавить транзакцию в мемпул. Возвращает False если уже есть."""
        async with self._lock:
            if tx.hash in self._transactions:
                return False
            tx.status = TxStatus.PENDING
            self._transactions[tx.hash] = tx
            self._new_tx_event.set()
            return True

    async def get_pending(self, limit: int = 100) -> list[Transaction]:
        """Взять пачку транзакций для майнинга и пометить их."""
        async with self._lock:
            pending = [tx for tx in self._transactions.values()
                       if tx.status == TxStatus.PENDING][:limit]
            for tx in pending:
                tx.status = TxStatus.MINING
            return pending

    async def remove_confirmed(self, tx_hashes: set[str]):
        """Удалить подтверждённые транзакции."""
        async with self._lock:
            for h in tx_hashes:
                self._transactions.pop(h, None)

    async def remove_transactions(self, tx_hashes: set[str]):
        """Удалить транзакции из mempool"""
        async with self._lock:
            for h in tx_hashes:
                self._transactions.pop(h, None)

    async def fail_transactions(self, tx_hashes: set[str]):
        """Вернуть транзакции обратно в pending"""
        async with self._lock:
            for h in tx_hashes:
                if h in self._transactions:
                    self._transactions[h].status = TxStatus.PENDING

    async def get_by_hash(self, tx_hash: str) -> Optional[Transaction]:
        async with self._lock:
            return self._transactions.get(tx_hash)

    async def count_pending(self) -> int:
        async with self._lock:
            return sum(1 for tx in self._transactions.values()
                       if tx.status == TxStatus.PENDING)

    async def wait_for_tasks(self, timeout: float = 5.0):
        """Ждать новые транзакции (для майнеров через long-poll)."""
        self._new_tx_event.clear()
        try:
            await asyncio.wait_for(self._new_tx_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass


mempool = Mempool()