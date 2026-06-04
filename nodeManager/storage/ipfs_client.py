import httpx
import json
import logging

from config import settings

logger = logging.getLogger(__name__)


class IPFSClient:
    """
    Работа с IPFS через ipfs-cluster.

    - Загрузка: через ipfs-cluster:9096 (кластер сам раскидывает по нодам)
    - Чтение: напрямую с локальной IPFS ноды (все файлы доступны по CID)
    - Пиннинг: не нужен — кластер сам управляет репликацией
    """

    def __init__(self):
        self._cluster: httpx.AsyncClient | None = None

    async def connect(self):
        self._cluster = httpx.AsyncClient(
            base_url=f"http://{settings.CLUSTER_HOST}:{settings.CLUSTER_PORT}",
            timeout=60.0,
        )
        logger.info(
            f"IPFS cluster connected: {settings.CLUSTER_HOST}:{settings.CLUSTER_PORT}"
        )

    async def add_file(self, data: bytes, filename: str = "") -> str:
        """Загрузить файл через кластер. Возвращает CID."""
        files = {"file": (filename or "file", data)}
        resp = await self._cluster.post("/add", files=files)
        resp.raise_for_status()
        result = resp.json()
        cid = result.get("Hash", "")
        logger.info(f"IPFS cluster: uploaded {filename or 'file'} -> {cid}")
        return result

    async def add_json(self, obj: dict) -> str:
        """Загрузить JSON через кластер. Возвращает CID."""
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return await self.add_file(data, "data.json")

    async def get_file(self, cid: str) -> bytes:
        """Скачать файл по CID (через локальный IPFS API)."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://{settings.IPFS_HOST}:{settings.IPFS_PORT}/api/v0/cat",
                params={"arg": cid},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.content

    async def get_json(self, cid: str) -> dict:
        """Скачать и распарсить JSON по CID."""
        raw = await self.get_file(cid)
        return json.loads(raw.decode())

    async def cluster_status(self) -> list:
        """Статус ipfs-cluster — список пиров."""
        try:
            resp = await self._cluster.get("/peers")
            return self._parse_ndjson(resp.text)
        except Exception as e:
            logger.error(f"cluster_status failed: {type(e).__name__}: {e}", exc_info=True)
            raise

    async def cluster_allocations(self) -> list:
        """Какие CID на каких нодах лежат."""
        try:
            resp = await self._cluster.get("/allocations")
            return self._parse_ndjson(resp.text)
        except Exception as e:
            logger.error(f"cluster_allocations failed: {type(e).__name__}: {e}", exc_info=True)
            raise

    async def get_file_info(self, cid: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://{settings.IPFS_HOST}:{settings.IPFS_PORT}/api/v0/dag/stat",
                params={"arg": cid},
                timeout=10.0,
            )
        resp.raise_for_status()
        return self._parse_ndjson(resp.text)

    @staticmethod
    def _parse_ndjson(text: str) -> list:
        """Парсит newline-delimited JSON (каждая строка — отдельный JSON)."""
        results = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results

    async def cluster_recover(self, cid: str):
        """Восстановить репликацию CID."""
        resp = await self._cluster.post(f"/pins/{cid}/recover")
        resp.raise_for_status()

    async def close(self):
        if self._cluster:
            await self._cluster.aclose()


# singleton
ipfs = IPFSClient()