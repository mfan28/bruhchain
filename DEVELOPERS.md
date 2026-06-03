# Документация для разработчиков приложений

## Обзор платформы

**NodeManager** — блокчейн-платформа для социального профилирования. Хранение блоков и транзакций — **Cassandra** (общий кластер, gossip-репликация), файлы — **IPFS**, состояние аккаунтов — **LevelDB** (локально на каждой ноде).

**Базовая архитектура:**

```
Ваше приложение ←→ NodeManager REST API
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Cassandra      LevelDB (State)     IPFS
   (блоки + TX)   (аккаунты, nonce)  (файлы)
```

**Ключевые особенности:**
- Нода **не хранит блоки локально** — они в общем Cassandra-кластере
- Каждая нода имеет **свой LevelDB** (State Trie), который переигрывается из блоков при старте
- Mempool — **только в памяти**, не синхронизируется между нодами
- Консенсус через **Cassandra LWT** (блокировки высот) + PoW

---

## 1. Модель аккаунта и состояние (State)

Каждый аккаунт — запись в LevelDB с ключом = адрес и значением = JSON.

**Минимальный аккаунт:**
```json
{
    "nonce": 0
}
```

Кастомные поля (например, `name`, `avatar`) добавляются транзакциями с `action: "state"`.

**Адрес аккаунта** — произвольная строка (например, `0xalice`). Система не валидирует адреса криптографически.

**Nonce** — счётчик транзакций аккаунта. Каждая новая транзакция должна иметь `nonce`, равный текущему nonce аккаунта. После применения nonce увеличивается на 1. Защита от replay attack.

---

## 2. Транзакция

Любое действие в системе — транзакция.

```json
{
    "from": "0xalice",
    "to": "0xbob",
    "nonce": 5,
    "payload": {
        "action": "state",
        "name": "Alice",
        "avatar": "Qm...",
        "message": "Hello!"
    },
    "signature": "0x...",
    "timestamp": 1717200000
}
```

### Поля

| Поле | Тип | Описание |
|------|-----|----------|
| `from` | string | Адрес отправителя |
| `to` | string | Адрес получателя |
| `nonce` | int | Текущий nonce отправителя |
| `payload` | object | Данные транзакции |
| `signature` | string | Подпись (строка, **не валидируется нодой**) |
| `timestamp` | int | Unix timestamp (секунды) |

### Payload и actions

| action | Что делает | Доп. поля payload |
|--------|-----------|-------------------|
| `state` | Обновить поля аккаунта | любые ключи (`name`, `avatar`, и т.д.) |
| `generic` | Просто увеличить nonce | не важны |
| любая другая | То же что generic | не важны |

### Жизненный цикл

```
Клиент → POST /api/v1/transaction → Mempool [PENDING]
                                        ↓ (майнер забирает)
                                   [MINING]
                                        ↓ (блок подтверждён)
                             Cassandra + LevelDB [CONFIRMED]
                                        ↓ (или ошибка nonce)
                                   удаляется из mempool
```

---

## 3. REST API

Базовый URL: `http://node:8000/api/v1`

### Транзакции

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/transaction` | Отправить транзакцию в mempool |
| `GET` | `/transaction/{hash}` | Статус транзакции |
| `GET` | `/transactions/{address}` | Все транзакции адреса |
| `GET` | `/transactions/recent?limit=20` | Последние транзакции |

**POST /transaction**
```json
// Request
{ "from": "0xalice", "to": "0xbob", "nonce": 0, "payload": {...}, "signature": "0x...", "timestamp": 1717200000 }

// Response
{ "hash": "abc123...", "status": "pending" }
```

**GET /transaction/{hash}**
```json
{
    "hash": "abc123...", "from": "0xalice", "to": "0xbob",
    "nonce": 0, "payload": {...}, "signature": "0x...",
    "timestamp": 1717200000, "block_height": 42, "status": "confirmed"
}
```

### Блоки

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/block/latest` | Последний блок |
| `GET` | `/blocks?limit=20&offset=0` | Список блоков (с пагинацией) |
| `GET` | `/block/{height}` | Блок по высоте |
| `GET` | `/block/search/hash?hash=` | Поиск блока по хешу |

**GET /block/{height}**
```json
{
    "height": 42, "hash": "0000abcd...", "previous_hash": "0000ef01...",
    "merkle_root": "ffff...", "state_root": "aaaa...", "difficulty": 5,
    "nonce": 123456, "miner_address": "0xminer", "timestamp": 1717200100,
    "tx_count": 3,
    "transactions": [
        { "hash": "tx1...", "from": "0xalice", "to": "0xbob", "payload": {...} }
    ]
}
```

### Аккаунты

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/account/{address}` | Данные аккаунта |
| `GET` | `/accounts` | Список всех аккаунтов |

### Майнинг

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/mine/task` | Получить задачу для майнинга |
| `POST` | `/mine/submit` | Отправить готовый блок |
| `GET` | `/mine/stats` | Статистика майнинга |
| `POST` | `/mine/difficulty` | Изменить сложность |

### IPFS

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/ipfs/{cid}` | Скачать файл |
| `GET` | `/ipfs/info/{cid}` | Метаинформация о файле |
| `POST` | `/ipfs/upload` | Загрузить файл (multipart) |

### Nodes

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/nodes` | Список всех нод в кластере |
| `POST` | `/node/register` | Ручная регистрация ноды |

### Cassandra Viewer

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/cassandra/tables` | Список таблиц |
| `GET` | `/cassandra/table/{table}?limit=20` | Содержимое таблицы |

### P2P (межнодовые)

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/p2p/block` | Уведомление о новом блоке от пира |
| `GET` | `/p2p/blocks?from_height=&limit=` | Получить блоки для синхронизации |

---

## 4. Хеши и консенсус

**Хеш транзакции:**
```
SHA256(from + to + nonce + payload(canonical JSON) + signature + timestamp)
```

**Merkle root:** бинарное дерево хешей транзакций (SHA256). При нечётном количестве — последний хеш дублируется.

**PoW хеш (для майнинга):**
```
SHA256(prev_hash + merkle_root + timestamp + difficulty + nonce + miner_address)
```
Условие: хеш начинается с `difficulty` нулей.

**Блок-хеш:**
```
SHA256(prev_hash + merkle_root + timestamp + difficulty + nonce + miner_address + state_root)
```

**State root:** SHA256 от конкатенации всех пар (address + value) из LevelDB, отсортированных по ключу.

---

## 5. Типичные сценарии использования

### Создание аккаунта

```python
import requests, hashlib, json, time

payload = {"action": "state", "name": "Alice", "avatar": "QmAvatarCID"}
raw = f"0xalice0xbob0{json.dumps(payload, sort_keys=True)}0xsign{int(time.time())}"
tx_hash = hashlib.sha256(raw.encode()).hexdigest()

resp = requests.post("http://localhost:8000/api/v1/transaction", json={
    "from": "0xalice", "to": "0xbob", "nonce": 0,
    "payload": payload, "signature": "0xsign",
    "timestamp": int(time.time()),
})
print(resp.json())
```

После майнинга блока — аккаунт появится в LevelDB с nonce=1 и полями из payload.

### Поиск блока по хешу

```python
resp = requests.get("http://localhost:8000/api/v1/block/search/hash?hash=0000abcd...")
block = resp.json()
print(f"Height: {block['height']}, TX: {block['tx_count']}")
```

---

## 6. Ограничения

- **Подпись не валидируется** — `signature` хранится как строка, нода её не проверяет
- **Mempool не синхронизируется** — транзакция, отправленная на ноду А, не попадёт в майнинг на ноде Б. Отправляйте туда, где майните
- **ALLOW FILTERING** — поиск блока по хешу использует `ALLOW FILTERING`, что неэффективно на больших данных
- **State Root** — линейный обход LevelDB, O(n) по числу аккаунтов

---

### 4.4. Блоки

#### Последний блок

**`GET /api/v1/block/latest`**

```json
{
    "height": 42,
    "hash": "0x...",
    "previous_hash": "0x...",
    "state_root": "0x...",
    "timestamp": 1717200000,
    "tx_count": 5
}
```

#### Список блоков (с пагинацией)

**`GET /api/v1/blocks?limit=20&offset=0`**

```json
{
    "blocks": [
        {
            "height": 42,
            "hash": "0x...",
            "previous_hash": "0x...",
            "timestamp": 1717200000,
            "tx_count": 5,
            "miner_address": "0xminer1",
            "difficulty": 4
        }
    ],
    "count": 1,
    "limit": 20,
    "offset": 0
}
```

#### Блок по высоте (с транзакциями)

**`GET /api/v1/block/{height}`**

```json
{
    "height": 42,
    "hash": "0x...",
    "previous_hash": "0x...",
    "merkle_root": "0x...",
    "state_root": "0x...",
    "difficulty": 4,
    "nonce": 128734,
    "miner_address": "0xminer1",
    "timestamp": 1717200000,
    "tx_count": 2,
    "transactions": [
        {
            "hash": "abc...",
            "from": "0xalice",
            "to": "0xbob",
            "payload": {"action": "send_message", "message": "Hi!"}
        }
    ]
}
```

---

### 4.5. IPFS

#### Загрузить файл

**`POST /api/v1/ipfs/upload`**

Request: `multipart/form-data` с полем `file`.

Response:
```json
{
    "cid": "Qm...",
    "filename": "photo.jpg",
    "size": 102400
}
```

#### Получить информацию о файле

**`GET /api/v1/ipfs/info/{cid}`**

```json
{
    "cid": "Qm...",
    "size": 102400,
    "preview": "hex...",
    "is_json": false
}
```

#### Скачать файл

**`GET /api/v1/ipfs/{cid}`**

Возвращает файл бинарно (`application/octet-stream`).

---

## 5. Полный сценарий работы приложения

### Шаг 1: Проверить статус ноды

```bash
curl http://localhost:8000/api/v1/
```

### Шаг 2: Зарегистрировать пользователя

Узнать текущий nonce (если аккаунт новый — 404, nonce = 0):

```bash
curl http://localhost:8000/api/v1/account/0xalice
# → 404 Not Found (аккаунт ещё не создан, nonce=0)
```

Отправить транзакцию создания аккаунта:

```bash
curl -X POST http://localhost:8000/api/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0xalice",
    "to": "0xalice",
    "nonce": 0,
    "payload": {
      "action": "create_account",
      "name": "Alice",
      "avatar": "",
      "description": "My first account"
    },
    "signature": "0xalice_sig_1",
    "timestamp": 1717200000
  }'
```

### Шаг 3: Дождаться майнинга

После отправки транзакция попадает в mempool и ждёт, пока майнер включит её в блок. Проверить статус:

```bash
curl http://localhost:8000/api/v1/transaction/<HASH>
# → "status": "confirmed"
```

### Шаг 4: Отправить сообщение

После подтверждения создания аккаунта nonce стал равен 1:

```bash
curl -X POST http://localhost:8000/api/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0xalice",
    "to": "0xbob",
    "nonce": 1,
    "payload": {
      "action": "send_message",
      "message": "Привет, Боб!"
    },
    "signature": "0xalice_sig_2",
    "timestamp": 1717200100
  }'
```

### Шаг 5: Прочитать сообщения

Транзакции от Alice к Bob (после майнинга):

```bash
curl http://localhost:8000/api/v1/transactions/received/0xbob
```

### Шаг 6: Загрузить аватарку в IPFS

```bash
curl -X POST http://localhost:8000/api/v1/ipfs/upload \
  -F "file=@avatar.jpg"
# → {"cid": "QmAbc123...", "filename": "avatar.jpg", "size": 65536}
```

И обновить профиль, указав CID аватарки:

```bash
curl -X POST http://localhost:8000/api/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0xalice",
    "to": "0xalice",
    "nonce": 2,
    "payload": {
      "action": "update_profile",
      "avatar": "QmAbc123..."
    },
    "signature": "0xalice_sig_3",
    "timestamp": 1717200200
  }'
```

---

## 6. Важные замечания

1. **Nonce обязателен** — каждая транзакция должна иметь `nonce`, равный текущему nonce отправителя. Иначе транзакция будет отклонена и удалена из mempool. Получить текущий nonce: `GET /api/v1/account/{address}`.

2. **Подпись не валидируется** — поле `signature` хранится, но нода не проверяет её криптографически. Это responsibility клиента.

3. **Timestamp** — Unix timestamp в секундах. Рекомендуется ставить `Math.floor(Date.now() / 1000)`.

4. **Транзакции не исполняются мгновенно** — они ждут майнера. В среднем блок майнится 10-60 секунд при сложности 4.

5. **Payload может быть любым** — структура не ограничена, поле `action` — это соглашение для читаемости.

6. **IPFS файлы сохраняются** — но не пингуются автоматически. Используйте внешний IPFS-cluster или пин-сервис для сохранения файлов.