"""
P2P Client — отправка уведомлений между нодами.
"""

import logging
import httpx

from config import settings

logger = logging.getLogger(__name__)


class P2PClient:
    """
    Лёгкий клиент для рассылки блоков всем пирам.
    """

    def __init__(self, timeout: float = 5.0):
        self._timeout = timeout

    async def broadcast_block(self, height: int, block_hash: str) -> int:
        """
        Разослать уведомление о новом блоке всем активным пирам.
        Возвращает количество успешно подтвердивших.
        """
        from db.cassandra import db

        peers = await db.get_active_nodes()
        our_id = settings.NODE_ID if hasattr(settings, 'NODE_ID') else ""

        sent = 0
        for peer in peers:
            if peer.node_id == our_id or peer.node_id == "":
                continue

            peer_url = f"http://{peer.api_host}:{peer.api_port}"
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{peer_url}/api/v1/p2p/block",
                        json={"height": height, "hash": block_hash},
                    )
                    if resp.is_success:
                        sent += 1
                    else:
                        logger.debug(f"Peer {peer.node_id} returned {resp.status_code}")
            except Exception as e:
                logger.debug(f"Peer {peer.node_id} unreachable: {e}")

        if sent:
            logger.info(f"Broadcast block #{height} to {sent}/{len(peers)} peers")
        return sent


# singleton
p2p_client = P2PClient()