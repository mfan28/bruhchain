import json
import hashlib
import os
from typing import Optional

import plyvel

from config import settings


class StateTrie:
    """
    Состояние аккаунтов (State Trie) на LevelDB (plyvel).
    Хранит: {address -> json(online, nonce, name, avatar, description, ...)}
    """

    def __init__(self):
        db_path = settings.STATE_DB_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db = plyvel.DB(db_path, create_if_missing=True)

    def get_account(self, address: str) -> Optional[dict]:
        data = self._db.get(address.encode())
        if data is None:
            return None
        return json.loads(data.decode())

    def put_account(self, address: str, data: dict):
        self._db.put(address.encode(), json.dumps(data).encode())

    def delete_account(self, address: str):
        self._db.delete(address.encode())

    def apply_transaction(self, tx) -> bool:
        """
        Применить транзакцию к состоянию.
        Возвращает True если успешно.
        """
        sender = self.get_account(tx.from_address)

        # Автосоздание аккаунта при первом обращении
        if sender is None:
            sender = {
                "nonce": 0,
            }

        # Проверка nonce — защита от replay attack
        if tx.nonce != sender["nonce"]:
            return False

        # Обработка payload
        payload = tx.payload
        action = payload.get("action", "generic")

        if action == "state":
            sender["nonce"] += 1
            for key, value in payload.items():
                if key != "action":
                    sender[key] = value
            self.put_account(tx.from_address, sender)
        elif action == "generic":
            sender["nonce"] += 1
            self.put_account(tx.from_address, sender)
        else:
            sender["nonce"] += 1
            self.put_account(tx.from_address, sender)

        return True

    def revert_transaction(self, tx):
        """Откатить транзакцию (для реорга)."""
        sender = self.get_account(tx.from_address)
        if sender:
            sender["nonce"] = max(0, sender["nonce"] - 1)
            self.put_account(tx.from_address, sender)

    def get_state_root(self) -> str:
        """
        Вычислить хеш корня состояния.
        Конкатенируем все пары address+data в отсортированном порядке и хешируем.
        """
        combined = b""
        for key, value in self._db:
            combined += key + value
        return hashlib.sha256(combined).hexdigest() if combined else hashlib.sha256(b"empty").hexdigest()

    def get_all_accounts(self) -> dict[str, dict]:
        """Получить все аккаунты."""
        result = {}
        for key, value in self._db:
            result[key.decode()] = json.loads(value.decode())
        return result

    def close(self):
        self._db.close()


# singleton
state_trie = StateTrie()