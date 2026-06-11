import hashlib
import json
import time
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from cassandra.query import SimpleStatement

from models.schemas import (
    Transaction, TransactionRequest, TxStatus,
    MiningTask, SubmitBlockRequest
)
from node.mempool import mempool
from node.blockchain import blockchain
from node.state import state_trie
from node.node_service import node_service
from db.cassandra import db
from config import settings
from storage.ipfs_client import ipfs

router = APIRouter()


@router.get("/")
async def root():
    last_block = await db.get_last_block()
    accounts = state_trie.get_all_accounts()
    chain_height = last_block.height if last_block else 0
    
    tx_count = 0
    if chain_height > 0:
        try:
            tx_query = SimpleStatement("SELECT COUNT(*) FROM transactions")
            tx_rows = list(db.session.execute(tx_query))
            if tx_rows:
                tx_count = tx_rows[0].count
        except:
            pass
    
    return {
        "service": "NodeManager",
        "status": "running",
        "chain_height": chain_height,
        "pending_txs": await mempool.count_pending(),
        "accounts_count": len(accounts),
        "total_txs": tx_count,
        "difficulty": settings.MINING_DIFFICULTY,
        "miner_address": settings.BLOCK_REWARD_ADDRESS or "",
    }


# ─── Транзакции ─────────────────────────────────────────────


@router.post("/transaction")
async def submit_transaction(req: TransactionRequest):
    """Клиент отправляет подписанную транзакцию."""
    # Вычисляем хеш
    raw = (
        f"{req.from_address}{req.to_address}{req.nonce}"
        f"{json.dumps(req.payload, sort_keys=True)}"
        f"{req.signature}{req.timestamp}"
    )
    tx_hash = hashlib.sha256(raw.encode()).hexdigest()

    tx = Transaction(
        hash=tx_hash,
        from_address=req.from_address,
        to_address=req.to_address,
        nonce=req.nonce,
        payload=req.payload,
        signature=req.signature,
        timestamp=req.timestamp or int(time.time()),
        status=TxStatus.PENDING,
    )

    ok = await mempool.add_transaction(tx)
    if not ok:
        raise HTTPException(409, "Transaction already in mempool")

    return {"hash": tx_hash, "status": TxStatus.PENDING}


@router.get("/transaction/{tx_hash}")
async def get_transaction(tx_hash: str):
    """Получить статус транзакции."""
    # Сначала смотрим в mempool
    tx = await mempool.get_by_hash(tx_hash)
    if tx:
        return tx.model_dump(by_alias=True)

    # Потом в Cassandra
    row = await db.get_transaction(tx_hash)
    if row:
        return {
            "hash": row.hash,
            "from": row.from_address,
            "to": row.to_address,
            "nonce": row.nonce,
            "payload": json.loads(row.payload),
            "signature": row.signature,
            "timestamp": row.timestamp,
            "block_height": row.block_height,
            "status": row.status,
        }

    raise HTTPException(404, "Transaction not found")


@router.get("/transactions/sent/{address}")
async def get_sent_transactions(address: str, limit: int = 50):
    """Транзакции, отправленные адресом."""
    rows = await db.get_transactions_by_address(address, limit)
    return _format_tx_list(rows)


@router.get("/transactions/received/{address}")
async def get_received_transactions(address: str, limit: int = 50):
    """Транзакции, полученные адресом."""
    rows = await db.get_transactions_to_address(address, limit)
    return _format_tx_list(rows)


@router.get("/transactions/{address}")
async def get_all_transactions(address: str, limit: int = 50):
    """Все транзакции адреса (отправленные + полученные)."""
    sent = await db.get_transactions_by_address(address, limit)
    received = await db.get_transactions_to_address(address, limit)

    # Объединяем и сортируем по времени (свежие сверху)
    all_txs = sent + received
    all_txs.sort(key=lambda r: r.timestamp, reverse=True)
    return _format_tx_list(all_txs[:limit])


def _format_tx_list(rows):
    result = []
    for row in rows:
        result.append({
            "hash": row.hash,
            "from": row.from_address,
            "to": row.to_address,
            "nonce": row.nonce,
            "payload": json.loads(row.payload) if isinstance(row.payload, str) else row.payload,
            "signature": row.signature,
            "timestamp": row.timestamp,
            "block_height": row.block_height,
            "status": row.status,
        })
    return {"transactions": result, "count": len(result)}


# ─── Майнинг ────────────────────────────────────────────────


@router.get("/mine/task")
async def get_mining_task():
    """Майнер получает задачу: список TX + сложность."""
    task = await blockchain.create_mining_task()
    return task.model_dump()


@router.post("/mine/submit")
async def submit_mined_block(req: SubmitBlockRequest):
    """Майнер отправляет готовый блок."""
    success, msg = await blockchain.submit_block(req)
    if not success:
        raise HTTPException(400, msg)
    return {"success": True, "block_hash": msg}


@router.get("/mine/stats")
async def mining_stats():
    """Статистика майнинга."""
    last_block = await db.get_last_block()
    chain_height = last_block.height if last_block else 0
    # Count total blocks mined by this node
    miner = settings.BLOCK_REWARD_ADDRESS or ""
    return {
        "difficulty": settings.MINING_DIFFICULTY,
        "chain_height": chain_height,
        "total_blocks": chain_height,
        "miner_address": miner,
    }


@router.post("/mine/difficulty")
async def set_difficulty(data: dict):
    """Изменить сложность майнинга (на лету)."""
    diff = data.get("difficulty")
    if not diff or not isinstance(diff, int) or diff < 1 or diff > 20:
        raise HTTPException(400, "Difficulty must be 1-20")
    settings.MINING_DIFFICULTY = diff
    return {"difficulty": diff}


# ─── Блоки ──────────────────────────────────────────────────


@router.get("/block/latest")
async def get_latest_block():
    last = await db.get_last_block()
    if not last:
        raise HTTPException(404, "No blocks yet")
    return {
        "height": last.height,
        "hash": last.hash,
        "previous_hash": last.previous_hash,
        "state_root": last.state_root,
        "timestamp": last.timestamp,
        "tx_count": last.tx_count,
    }


@router.get("/blocks")
async def get_blocks(limit: int = 20, offset: int = 0):
    """Список блоков с пагинацией."""
    rows = await db.get_blocks(limit, offset)
    return {
        "blocks": [
            {
                "height": r.height,
                "hash": r.hash,
                "previous_hash": r.previous_hash,
                "timestamp": r.timestamp,
                "tx_count": r.tx_count,
                "miner_address": r.miner_address,
                "difficulty": r.difficulty,
            }
            for r in rows
        ],
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.get("/block/{height}")
async def get_block(height: int):
    block = await db.get_block_by_height(height)
    if not block:
        raise HTTPException(404, "Block not found")
    txs = await db.get_block_transactions(height)
    return {
        "height": block.height,
        "hash": block.hash,
        "previous_hash": block.previous_hash,
        "merkle_root": block.merkle_root,
        "state_root": block.state_root,
        "difficulty": block.difficulty,
        "nonce": block.nonce,
        "miner_address": block.miner_address,
        "timestamp": block.timestamp,
        "tx_count": block.tx_count,
        "transactions": [
            {
                "hash": tx.hash,
                "from": tx.from_address,
                "to": tx.to_address,
                "payload": json.loads(tx.payload),
            }
            for tx in txs
        ],
    }


@router.get("/block/search/hash")
async def get_block_by_hash(hash: str):
    """Поиск блока по хешу."""
    block = await db.get_block_by_hash(hash)
    if not block:
        raise HTTPException(404, "Block not found")
    txs = await db.get_block_transactions(block.height)
    return {
        "height": block.height,
        "hash": block.hash,
        "previous_hash": block.previous_hash,
        "merkle_root": block.merkle_root,
        "state_root": block.state_root,
        "difficulty": block.difficulty,
        "nonce": block.nonce,
        "miner_address": block.miner_address,
        "timestamp": block.timestamp,
        "tx_count": block.tx_count,
        "transactions": [
            {
                "hash": tx.hash,
                "from": tx.from_address,
                "to": tx.to_address,
                "payload": json.loads(tx.payload),
            }
            for tx in txs
        ],
    }


# ─── Аккаунты / State ──────────────────────────────────────


@router.get("/account/{address}")
async def get_account(address: str):
    acc = state_trie.get_account(address)
    if acc is None:
        raise HTTPException(404, "Account not found")
    return {"address": address, **acc}


@router.get("/accounts")
async def list_accounts():
    """Список всех аккаунтов."""
    accounts = state_trie.get_all_accounts()
    result = [{"address": addr, **data} for addr, data in accounts.items()]
    result.sort(key=lambda a: a.get("nonce", 0), reverse=True)
    return {"accounts": result, "count": len(result)}


@router.get("/transactions/recent")
async def recent_transactions(limit: int = 20):
    """Последние транзакции (из последних блоков)."""
    last_block = await db.get_last_block()
    if not last_block:
        return {"transactions": [], "count": 0}
    height = last_block.height
    result = []
    # Собираем транзакции из последних N блоков
    while height >= 0 and len(result) < limit:
        txs = await db.get_block_transactions(height)
        result.extend(txs)
        height -= 1
    return _format_tx_list(result[:limit])


# ─── IPFS ───────────────────────────────────────────────────

import logging
_log = logging.getLogger(__name__)


@router.get("/ipfs/cluster/peers")
async def ipfs_cluster_peers():
    """Список пиров ipfs-cluster."""
    try:
        data = await ipfs.cluster_status()
        return data
    except Exception as e:
        _log.error(f"Cluster peers error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(502, f"Cluster unreachable: {type(e).__name__}: {e}")


@router.get("/ipfs/cluster/allocations")
async def ipfs_cluster_allocations():
    """Файлы и на каких нодах лежат."""
    try:
        data = await ipfs.cluster_allocations()
        return data
    except Exception as e:
        raise HTTPException(502, f"Cluster unreachable: {e}")


@router.post("/ipfs/cluster/recover/{cid}")
async def ipfs_cluster_recover(cid: str):
    """Восстановить репликацию CID."""
    try:
        await ipfs.cluster_recover(cid)
        return {"status": "ok", "cid": cid}
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/ipfs/{cid}")
async def get_ipfs_file(cid: str):
    """Получить файл из IPFS по CID."""
    try:
        data = await ipfs.get_file(cid)
        return Response(content=data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename=\"{cid}\""})
    except Exception as e:
        raise HTTPException(404, str(e))


@router.post("/ipfs/upload")
async def upload_ipfs_file(file: UploadFile = File(...)):
    """Загрузить файл в IPFS."""
    data = await file.read()
    cid = await ipfs.add_file(data, file.filename or "")
    return {"cid": cid, "filename": file.filename, "size": len(data)}


@router.get("/ipfs/info/{cid}")
async def get_ipfs_file_info(cid: str):
    try:
        return await ipfs.get_file_info(cid)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Nodes ──────────────────────────────────────────────────


@router.get("/nodes")
async def get_nodes():
    """Список всех зарегистрированных нод."""
    rows = await db.get_all_nodes()
    return {
        "nodes": [
            {
                "node_id": r.node_id,
                "name": r.name,
                "api_host": r.api_host,
                "api_port": r.api_port,
                "chain_height": r.chain_height,
                "last_seen": r.last_seen,
                "is_active": r.is_active,
                "is_self": r.node_id == node_service.node_id,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/node/register")
async def register_node(node_info: dict):
    """Зарегистрировать новую ноду вручную (через UI)."""
    node_id = node_info.get("node_id", "")
    if not node_id:
        raise HTTPException(400, "node_id required")
    await db.register_node(
        node_id=node_id,
        name=node_info.get("name", node_id),
        api_host=node_info.get("api_host", ""),
        api_port=node_info.get("api_port", 8000),
    )
    return {"status": "registered", "node_id": node_id}


# ─── Cassandra Viewer ──────────────────────────────────────


@router.get("/cassandra/tables")
async def cassandra_tables():
    """Список таблиц в Cassandra."""
    rows = db.session.execute(
        "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
        (settings.CASSANDRA_KEYSPACE,)
    )
    tables = [row.table_name for row in rows]
    return {"tables": tables}


@router.get("/cassandra/table/{table_name}")
async def cassandra_table(table_name: str, limit: int = 20):
    """Просмотр содержимого таблицы Cassandra (первые N строк)."""
    allowed = {"blocks", "transactions", "transactions_by_block",
               "transactions_by_from", "transactions_by_to", "nodes", "mining_locks"}
    if table_name not in allowed:
        raise HTTPException(403, f"Table '{table_name}' is not allowed")

    query = SimpleStatement(f"SELECT * FROM {table_name} LIMIT %s")
    rows = list(db.session.execute(query, (limit,)))

    if not rows:
        return {"table": table_name, "rows": [], "count": 0}

    columns = list(rows[0]._fields)
    data = []
    for row in rows:
        data.append({col: getattr(row, col) for col in columns})

    return {"table": table_name, "columns": columns, "rows": data, "count": len(data)}