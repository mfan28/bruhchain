import json
import time
from typing import Optional
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, ConsistencyLevel

from config import settings


class CassandraDB:
    """Работа с Cassandra — хранение блоков и транзакций."""

    def __init__(self):
        self.cluster = None
        self.session = None

    async def connect(self):
        self.cluster = Cluster([settings.CASSANDRA_HOST], port=settings.CASSANDRA_PORT)
        self.session = self.cluster.connect()
        self.session.default_consistency_level = ConsistencyLevel.QUORUM

        # Считаем сколько нод в кластере
        peers = list(self.session.execute("SELECT peer FROM system.peers"))
        node_count = 1 + len(peers)  # 1 (себя) + пиры
        rf = max(1, node_count)      # RF не меньше 2, даже если 1 нода

        self.session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS blockchain
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': {rf}}}
        """)
        self.session.set_keyspace(settings.CASSANDRA_KEYSPACE)

        # Апдейтим RF под текущее количество нод
        self.session.execute(f"""
            ALTER KEYSPACE blockchain
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': {rf}}}
        """)

        # Создаём таблицы (IF NOT EXISTS — безопасно для мульти-нод)
        self.session.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id text PRIMARY KEY,
                name text,
                api_host text,
                api_port int,
                ipfs_multiaddr text,
                cassandra_host text,
                cassandra_port int,
                chain_height bigint,
                last_seen bigint,
                is_active boolean,
                joined_at bigint
            )
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                partition int,
                height bigint,
                hash text,
                previous_hash text,
                merkle_root text,
                state_root text,
                difficulty int,
                nonce bigint,
                miner_address text,
                timestamp bigint,
                tx_count int,
                PRIMARY KEY (partition, height)
            ) WITH CLUSTERING ORDER BY (height DESC)
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                hash text PRIMARY KEY,
                from_address text,
                to_address text,
                nonce bigint,
                payload text,
                signature text,
                timestamp bigint,
                block_height bigint,
                status text
            )
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS transactions_by_block (
                block_height bigint,
                tx_hash text,
                PRIMARY KEY (block_height, tx_hash)
            )
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS transactions_by_from (
                from_address text,
                timestamp bigint,
                tx_hash text,
                PRIMARY KEY (from_address, timestamp)
            ) WITH CLUSTERING ORDER BY (timestamp DESC)
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS transactions_by_to (
                to_address text,
                timestamp bigint,
                tx_hash text,
                PRIMARY KEY (to_address, timestamp)
            ) WITH CLUSTERING ORDER BY (timestamp DESC)
        """)

        self.session.execute("""
            CREATE TABLE IF NOT EXISTS mining_locks (
                height bigint PRIMARY KEY,
                node_id text,
                locked_at bigint
            )
        """)

    async def save_block(self, block) -> str:
        """Сохранить блок. Возвращает хеш."""
        self.session.execute("""
            INSERT INTO blocks (partition, height, hash, previous_hash, merkle_root, state_root,
                                difficulty, nonce, miner_address, timestamp, tx_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            0, block.height, block.hash, block.header.previous_hash,
            block.header.merkle_root, block.header.state_root,
            block.header.difficulty, block.header.nonce,
            block.header.miner_address, block.header.timestamp,
            len(block.transactions)
        ))
        return block.hash

    async def save_transactions(self, txs: list, block_height: int):
        """Сохранить транзакции блока."""
        for tx in txs:
            self.session.execute("""
                INSERT INTO transactions (hash, from_address, to_address, nonce,
                                          payload, signature, timestamp, block_height, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                tx.hash, tx.from_address, tx.to_address, tx.nonce,
                json.dumps(tx.payload), tx.signature, tx.timestamp,
                block_height, "confirmed"
            ))
            self.session.execute("""
                INSERT INTO transactions_by_block (block_height, tx_hash)
                VALUES (%s, %s)
            """, (block_height, tx.hash))
            self.session.execute("""
                INSERT INTO transactions_by_from (from_address, timestamp, tx_hash)
                VALUES (%s, %s, %s)
            """, (tx.from_address, tx.timestamp, tx.hash))
            self.session.execute("""
                INSERT INTO transactions_by_to (to_address, timestamp, tx_hash)
                VALUES (%s, %s, %s)
            """, (tx.to_address, tx.timestamp, tx.hash))

    async def get_last_block(self):
        """Получить последний блок (с максимальной высотой)."""
        query = SimpleStatement(
            "SELECT * FROM blocks WHERE partition = 0 LIMIT 1"
        )
        # CLUSTERING ORDER BY (height DESC) — первая строка = последний блок
        rows = self.session.execute(query)
        for row in rows:
            return row
        return None

    async def get_blocks(self, limit: int = 20, offset: int = 0):
        """Список блоков с пагинацией (свежие сверху)."""
        query = SimpleStatement(
            "SELECT * FROM blocks WHERE partition = 0 LIMIT %s"
        )
        all_rows = list(self.session.execute(query, (offset + limit,)))
        return all_rows[offset:offset + limit]

    async def get_block_by_height(self, height: int):
        query = SimpleStatement("SELECT * FROM blocks WHERE partition = 0 AND height = %s")
        rows = self.session.execute(query, (height,))
        for row in rows:
            return row
        return None

    async def get_block_by_hash(self, block_hash: str):
        """Поиск блока по хешу (требует ALLOW FILTERING)."""
        query = SimpleStatement(
            "SELECT * FROM blocks WHERE partition = 0 AND hash = %s ALLOW FILTERING"
        )
        rows = self.session.execute(query, (block_hash,))
        for row in rows:
            return row
        return None

    async def get_transaction(self, tx_hash: str):
        query = SimpleStatement("SELECT * FROM transactions WHERE hash = %s")
        rows = self.session.execute(query, (tx_hash,))
        for row in rows:
            return row
        return None

    async def get_block_transactions(self, block_height: int):
        """Получить все транзакции блока."""
        query = SimpleStatement(
            "SELECT tx_hash FROM transactions_by_block WHERE block_height = %s"
        )
        rows = self.session.execute(query, (block_height,))
        hashes = [row.tx_hash for row in rows]
        if not hashes:
            return []
        # Запрашиваем каждую транзакцию отдельно (надёжнее чем IN)
        result = []
        for tx_hash in hashes:
            tx = await self.get_transaction(tx_hash)
            if tx:
                result.append(tx)
        return result

    async def get_transactions_by_address(self, address: str, limit: int = 50):
        """Транзакции, отправленные адресом."""
        return self._fetch_tx_by_index(
            "transactions_by_from", "from_address", address, limit
        )

    async def get_transactions_to_address(self, address: str, limit: int = 50):
        """Транзакции, полученные адресом."""
        return self._fetch_tx_by_index(
            "transactions_by_to", "to_address", address, limit
        )

    def _fetch_tx_by_index(self, table: str, col: str, address: str, limit: int):
        query = SimpleStatement(
            f"SELECT tx_hash FROM {table} WHERE {col} = %s LIMIT %s"
        )
        rows = self.session.execute(query, (address, limit))
        hashes = [row.tx_hash for row in rows]
        if not hashes:
            return []
        placeholders = ",".join(["%s"] * len(hashes))
        query = SimpleStatement(
            f"SELECT * FROM transactions WHERE hash IN ({placeholders})"
        )
        return list(self.session.execute(query, hashes))

    # ─── Node Registry ──────────────────────────────────────────

    async def register_node(self, node_id: str, name: str, api_host: str,
                            api_port: int, ipfs_multiaddr: str = "",
                            cassandra_host: str = "", cassandra_port: int = 9042):
        """Зарегистрировать или обновить информацию о ноде."""
        now = int(time.time())
        self.session.execute("""
            INSERT INTO nodes (node_id, name, api_host, api_port, ipfs_multiaddr,
                               cassandra_host, cassandra_port, chain_height,
                               last_seen, is_active, joined_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (node_id, name, api_host, api_port, ipfs_multiaddr,
              cassandra_host, cassandra_port, 0, now, True, now))

    async def update_node_heartbeat(self, node_id: str, chain_height: int = 0):
        """Обновить last_seen ноды."""
        now = int(time.time())
        self.session.execute("""
            UPDATE nodes SET last_seen = %s, chain_height = %s, is_active = %s
            WHERE node_id = %s
        """, (now, chain_height, True, node_id))

    async def get_active_nodes(self) -> list:
        """Получить все активные ноды."""
        query = SimpleStatement(
            "SELECT * FROM nodes WHERE is_active = True ALLOW FILTERING"
        )
        return list(self.session.execute(query))

    async def get_all_nodes(self) -> list:
        """Получить все зарегистрированные ноды."""
        query = SimpleStatement("SELECT * FROM nodes")
        return list(self.session.execute(query))

    async def mark_node_inactive(self, node_id: str):
        """Пометить ноду как неактивную."""
        self.session.execute(
            "UPDATE nodes SET is_active = False WHERE node_id = %s",
            (node_id,)
        )

    async def get_blocks_since(self, from_height: int, limit: int = 100):
        """
        Получить блоки начиная с определённой высоты.
        Важно: ORDER BY height ASC для правильного порядка переигровки.
        """
        # Используем ALLOW FILTERING т.к. height — clustering key, не partition key
        # Но т.к. partition = 0 фиксированный, запрос эффективен
        query = SimpleStatement(
            "SELECT * FROM blocks WHERE partition = 0 AND height >= %s "
            "ORDER BY height ASC LIMIT %s"
        )
        rows = self.session.execute(query, (from_height, limit))
        result = []
        for row in rows:
            result.append({
                "height": row.height,
                "hash": row.hash,
                "previous_hash": row.previous_hash,
                "merkle_root": row.merkle_root,
                "state_root": row.state_root,
                "difficulty": row.difficulty,
                "nonce": row.nonce,
                "miner_address": row.miner_address,
                "timestamp": row.timestamp,
                "tx_count": row.tx_count,
            })
        return result

    # ─── Mining Locks ──────────────────────────────────────────

    async def acquire_mining_lock(self, height: int, node_id: str) -> bool:
        """
        Попытаться заблокировать высоту для майнинга.
        Использует LWT (SERIAL + IF NOT EXISTS) — атомарно.
        Возвращает True если успешно (блокировка не занята).
        """
        now = int(time.time())

        # Атомарная вставка — только если записи нет
        result = self.session.execute(
            "INSERT INTO mining_locks (height, node_id, locked_at) "
            "VALUES (%s, %s, %s) IF NOT EXISTS",
            (height, node_id, now),
            consistency_level=ConsistencyLevel.SERIAL
        )
        if result.one().applied:
            return True

        # Не вставилось — проверяем не истекла ли блокировка
        row = result.one()
        if row and row.locked_at and (now - row.locked_at) >= 120:
            # Истекла — удаляем и пробуем ещё раз
            self.session.execute(
                "DELETE FROM mining_locks WHERE height = %s", (height,),
                consistency_level=ConsistencyLevel.QUORUM
            )
            return await self.acquire_mining_lock(height, node_id)

        return False

    async def release_mining_lock(self, height: int):
        """Снять блокировку с высоты."""
        self.session.execute(
            "DELETE FROM mining_locks WHERE height = %s", (height,)
        )

    async def get_mining_lock(self, height: int) -> Optional[str]:
        """Узнать какая нода заблокировала высоту. None если свободно."""
        query = SimpleStatement("SELECT * FROM mining_locks WHERE height = %s")
        rows = list(self.session.execute(query, (height,)))
        for row in rows:
            now = int(time.time())
            if row.locked_at and (now - row.locked_at) < 120:
                return row.node_id
            # Истекла — удаляем
            self.session.execute(
                "DELETE FROM mining_locks WHERE height = %s", (height,)
            )
        return None


# singleton
db = CassandraDB()