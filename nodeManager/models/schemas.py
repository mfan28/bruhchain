from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class TxStatus(str, Enum):
    PENDING = "pending"
    MINING = "mining"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Transaction(BaseModel):
    """Подписанная транзакция — пользовательский пакет данных."""
    hash: str = ""
    from_address: str = Field(..., alias="from")
    to_address: str = Field(..., alias="to")
    nonce: int
    payload: dict[str, Any]
    signature: str
    timestamp: int = 0
    status: TxStatus = TxStatus.PENDING
    block_hash: Optional[str] = None

    class Config:
        populate_by_name = True


class TransactionRequest(BaseModel):
    """Транзакция от клиента (без хеша и статуса)."""
    from_address: str = Field(..., alias="from")
    to_address: str = Field(..., alias="to")
    nonce: int
    payload: dict[str, Any]
    signature: str
    timestamp: int = 0

    class Config:
        populate_by_name = True


class BlockHeader(BaseModel):
    previous_hash: str
    merkle_root: str
    timestamp: int
    difficulty: int
    nonce: int
    miner_address: str
    state_root: str  # хеш корня State Trie после применения блока


class Block(BaseModel):
    hash: str = ""
    header: BlockHeader
    transactions: list[Transaction]
    height: int = 0


class MiningTask(BaseModel):
    """Задача для майнера."""
    task_id: str
    previous_hash: str
    merkle_root: str  # <-- добавили merkle_root
    transactions: list[Transaction]
    difficulty: int
    timestamp: int
    reward_address: str


class SubmitBlockRequest(BaseModel):
    """Майнер отправляет готовый блок."""
    task_id: str
    nonce: int
    miner_address: str
    timestamp: int