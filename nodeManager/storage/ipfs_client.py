import ipfshttpclient
from config import settings


class IPFSClient:
    """Работа с IPFS — хранение файлов (аватарки, документы, etc)."""

    def __init__(self):
        self._client = None

    async def connect(self):
        self._client = ipfshttpclient.connect(
            f"/dns/{settings.IPFS_HOST}/tcp/{settings.IPFS_PORT}/http"
        )

    async def add_file(self, data: bytes, filename: str = "") -> str:
        """Загрузить файл в IPFS. Возвращает CID."""
        res = self._client.add_bytes(data)
        return res  # строка CID

    async def add_json(self, obj: dict) -> str:
        """Загрузить JSON в IPFS. Возвращает CID."""
        import json
        res = self._client.add_json(json.dumps(obj))
        return res

    async def get_file(self, cid: str) -> bytes:
        """Скачать файл по CID."""
        return self._client.cat(cid)

    async def get_json(self, cid: str) -> dict:
        """Скачать и распарсить JSON по CID."""
        import json
        raw = self._client.cat(cid)
        return json.loads(raw.decode())

    async def pin(self, cid: str):
        """Закрепить файл (чтобы не удалился сборщиком мусора)."""
        self._client.pin.add(cid)

    async def unpin(self, cid: str):
        self._client.pin.remove(cid)

    async def close(self):
        if self._client:
            self._client.close()


# singleton
ipfs = IPFSClient()