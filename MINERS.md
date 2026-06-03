# Документация для майнеров

## Что такое майнинг в NodeManager?

Майнинг — это процесс поиска **nonce** такого, чтобы хеш блока удовлетворял условию Proof-of-Work (PoW). Майнер забирает транзакции из mempool, вычисляет для них хеш с разными nonce, и когда находит подходящий — отправляет блок на ноду.

**Сложность (difficulty)** — количество ведущих нулей в хеше. При difficulty=4 хеш должен начинаться с `0000...`.

---

## 1. Протокол майнинга (шаг за шагом)

### Шаг 1: Получить задачу

```
GET /api/v1/mine/task
```

Ответ:
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "previous_hash": "0000abc123def456...",
    "merkle_root": "ffff0011...",
    "transactions": [
        {"hash": "tx1...", "from": "0xalice", "to": "0xbob", "nonce": 0, "payload": {...}, "signature": "0x...", "timestamp": 1717200000, "status": "mining"},
        {"hash": "tx2...", ...}
    ],
    "difficulty": 4,
    "timestamp": 1717200100,
    "reward_address": "0xreward"
}
```

| Поле | Описание |
|------|----------|
| `task_id` | UUID задачи. Обязателен при сабмите |
| `previous_hash` | Хеш последнего блока в цепи (64 hex-символа) |
| `merkle_root` | Merkle root всех транзакций задачи (64 hex-символа) |
| `transactions` | Список транзакций для включения в блок |
| `difficulty` | Текущая сложность PoW |
| `timestamp` | **Единый** timestamp для майнинга и сабмита |
| `reward_address` | Адрес для награды (настраивается нодой) |

**Важно:** Если транзакций нет, майнер ждёт до 5 секунд. Если за это время транзакции не появились — возвращается задача с `task_id: "empty"` и пустым списком транзакций. В этом случае майнер должен повторить запрос через некоторое время.

**Особенность: `task_id: "locked"`** — если другая нода уже заблокировала эту высоту для майнинга, возвращается задача с `task_id: "locked"`. Майнер должен подождать и повторить запрос — блок скоро появится.

### Как работает блокировка высоты

Ноды используют **Cassandra LWT** (Lightweight Transaction) для эксклюзивного захвата высоты:

1. Нода вызывает `INSERT INTO mining_locks (height, node_id, locked_at) VALUES (...) IF NOT EXISTS` с `ConsistencyLevel.SERIAL` (Paxos-консенсус)
2. Если вставка прошла — только эта нода майнит эту высоту
3. Если нет — другая нода уже майнит
4. Лок живёт 120 секунд (TTL), после этого автоматически снимается
5. После успешного майнинга — лок удаляется, блок бродкастится всем пирам

### Шаг 2: Вычислить PoW (найти nonce)

Формула хеша для майнинга:

```
pow_hash = SHA256(
    previous_hash + merkle_root + timestamp + difficulty + nonce + miner_address
)
```

Параметры — всё строки, подаются на вход **как есть** (конкатенация строк, без разделителей).

Условие: `pow_hash.startsWith("0".repeat(difficulty))`

**Пример (Python):**

```python
import hashlib

def compute_pow_hash(previous_hash: str, merkle_root: str, timestamp: int,
                     difficulty: int, nonce: int, miner_address: str) -> str:
    raw = f"{previous_hash}{merkle_root}{timestamp}{difficulty}{nonce}{miner_address}"
    return hashlib.sha256(raw.encode()).hexdigest()

def mine(previous_hash: str, merkle_root: str, timestamp: int,
         difficulty: int, miner_address: str) -> tuple[int, str]:
    target = "0" * difficulty
    nonce = 0
    while True:
        h = compute_pow_hash(previous_hash, merkle_root, timestamp, difficulty, nonce, miner_address)
        if h.startswith(target):
            return nonce, h
        nonce += 1
```

**Пример (JavaScript / браузер):**

```javascript
async function sha256(data) {
    const encoder = new TextEncoder();
    const bytes = encoder.encode(data);
    const hashBuffer = await crypto.subtle.digest('SHA-256', bytes);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function mine(task, minerAddress) {
    const target = '0'.repeat(task.difficulty);
    let nonce = 0;
    while (true) {
        const data = task.previous_hash + task.merkle_root + task.timestamp + task.difficulty + nonce + minerAddress;
        const hash = await sha256(data);
        if (hash.startsWith(target)) {
            return { nonce, hash };
        }
        nonce++;
    }
}
```

**Критически важно:** `timestamp` для майнинга и сабмита должен быть **одним и тем же** — берите его из задачи (`task.timestamp`), не генерируйте новый!

### Шаг 3: Отправить блок

```
POST /api/v1/mine/submit
Content-Type: application/json

{
    "task_id": "550e8400-...",
    "nonce": 128734,
    "miner_address": "0xminer1",
    "timestamp": 1717200100
}
```

| Поле | Описание |
|------|----------|
| `task_id` | ID из задачи (обязательно) |
| `nonce` | Найденный nonce |
| `miner_address` | Ваш адрес майнера |
| `timestamp` | **Тот же** timestamp, что был в задаче |

Успешный ответ:
```json
{
    "success": true,
    "block_hash": "0000abcd..."
}
```

Ответ при ошибке (HTTP 400):
```json
{
    "detail": "PoW verification failed"
}
```

Возможные ошибки:
| Ошибка | Причина |
|--------|---------|
| `Unknown or expired task` | Task_id невалидный или задача уже обработана |
| `PoW verification failed` | nonce не подходит под условие difficulty |
| `Bad nonce in tx ... — removed from mempool` | У одной из транзакций nonce не совпал с состоянием аккаунта |

---

## 2. Алгоритм работы майнера (псевдокод)

```
while True:
    # 1. Получить задачу
    task = GET /api/v1/mine/task
    
    if task.task_id == "empty":
        sleep(3 seconds)
        continue
    
    if task.task_id == "locked":
        # Другая нода майнит эту высоту — ждём и пробуем снова
        sleep(2 seconds)
        continue
    
    # 2. Майнить
    (nonce, hash) = mine_PoW(
        previous_hash = task.previous_hash,
        merkle_root   = task.merkle_root,
        timestamp     = task.timestamp,  # !!! из задачи
        difficulty    = task.difficulty,
        miner_address = "0xmy_address"
    )
    
    # 3. Отправить
    result = POST /api/v1/mine/submit {
        task_id:        task.task_id,
        nonce:          nonce,
        miner_address:  "0xmy_address",
        timestamp:      task.timestamp   # !!! тот же
    }
    
    if result.success:
        # Блок принят — сразу берём следующую задачу
        continue
    else:
        # Ошибка — повторить
        sleep(1 second)
```

---

## 3. Написание своего майнера (пример на Python)

```python
import hashlib
import time
import requests

API = "http://localhost:8000/api/v1"
MINER_ADDRESS = "0xmy_miner"

def compute_pow_hash(prev_hash, merkle_root, timestamp, difficulty, nonce, miner):
    raw = f"{prev_hash}{merkle_root}{timestamp}{difficulty}{nonce}{miner}"
    return hashlib.sha256(raw.encode()).hexdigest()

def mine_task(task):
    target = "0" * task["difficulty"]
    nonce = 0
    while True:
        h = compute_pow_hash(
            task["previous_hash"], task["merkle_root"],
            task["timestamp"], task["difficulty"],
            nonce, MINER_ADDRESS
        )
        if h.startswith(target):
            return nonce
        nonce += 1
        # Опционально: прогресс каждые 100k хешей
        if nonce % 100000 == 0:
            print(f"  Tried {nonce} hashes...")

def main():
    print(f"🧊 Miner started: {MINER_ADDRESS}")
    while True:
        try:
            # 1. Получить задачу
            resp = requests.get(f"{API}/mine/task")
            task = resp.json()
            
            if task["task_id"] == "empty":
                print("⏳ No transactions, waiting...")
                time.sleep(3)
                continue

            if task["task_id"] == "locked":
                print("🔒 Height locked by another node, waiting...")
                time.sleep(2)
                continue

            print(f"📦 Task {task['task_id'][:8]}... | "
                  f"{len(task['transactions'])} tx(s) | "
                  f"difficulty {task['difficulty']}")
            
            # 2. Майнить
            start = time.time()
            nonce = mine_task(task)
            elapsed = time.time() - start
            print(f"🎯 Found nonce {nonce} in {elapsed:.1f}s")
            
            # 3. Сабмит
            resp = requests.post(f"{API}/mine/submit", json={
                "task_id": task["task_id"],
                "nonce": nonce,
                "miner_address": MINER_ADDRESS,
                "timestamp": task["timestamp"],  # !!! из задачи
            })
            result = resp.json()
            
            if resp.status_code == 200:
                print(f"✅ Block mined! hash: {result['block_hash'][:16]}...")
            else:
                print(f"❌ Submit failed: {result.get('detail', 'unknown')}")
                time.sleep(1)
                
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
```

---

## 4. Оптимизация майнинга

### 4.1. Пакетная обработка (batch)

Вместо одного хеша за раз — считайте пачками для снижения накладных расходов:

```python
BATCH_SIZE = 10000
while True:
    for _ in range(BATCH_SIZE):
        h = compute_pow_hash(...)
        if h.startswith(target):
            return nonce
        nonce += 1
    # Опционально: проверить, не появилась ли новая задача
    # (если блок уже нашёл другой майнер)
```

### 4.2. Многопоточный майнинг

Разделите пространство nonce между потоками:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def mine_range(prev_hash, merkle_root, timestamp, difficulty, miner, start_nonce, end_nonce):
    target = "0" * difficulty
    for nonce in range(start_nonce, end_nonce):
        h = compute_pow_hash(prev_hash, merkle_root, timestamp, difficulty, nonce, miner)
        if h.startswith(target):
            return nonce
    return None

def mine_parallel(task, num_threads=4):
    step = 1000000 // num_threads
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_threads):
            futures.append(executor.submit(
                mine_range,
                task["previous_hash"], task["merkle_root"],
                task["timestamp"], task["difficulty"],
                MINER_ADDRESS, i * step, (i + 1) * step
            ))
        for f in as_completed(futures):
            result = f.result()
            if result is not None:
                return result
    return None  # не нашли — расширить диапазон
```

### 4.3. GPU-майнинг

SHA256 на GPU (CUDA/OpenCL) может дать **100-1000x ускорение**. Используйте:
- **C++/CUDA**: библиотека `openssl` + ядро CUDA для SHA256
- **Python**: `pyopencl` + кастомное ядро SHA256
- **Node.js**: `webgpu` (экспериментально)

---

## 5. Проверка корректности майнера

Самопроверка: взять задачу, посчитать хеш, проверить что он совпадает с серверным.

**Формула для самопроверки:**

```python
def compute_block_hash(previous_hash, merkle_root, timestamp, difficulty, nonce, miner_address, state_root):
    raw = f"{previous_hash}{merkle_root}{timestamp}{difficulty}{nonce}{miner_address}{state_root}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

**Отличие хеша майнинга от хеша блока:**
- **PoW хеш** (считает майнер): `SHA256(prev + merkle + ts + diff + nonce + miner)` — **без** state_root
- **Block хеш** (считает нода): `SHA256(prev + merkle + ts + diff + nonce + miner + state_root)` — **с** state_root

Майнер не может знать state_root заранее, поэтому PoW проверяется без него.

---

## 6. Эндпоинты для майнера (сводка)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/mine/task` | GET | Получить задачу |
| `/api/v1/mine/submit` | POST | Отправить готовый блок |
| `/api/v1/block/latest` | GET | Получить последний блок (проверить высоту) |
| `/api/v1/account/{address}` | GET | Получить состояние аккаунта майнера |

---

## 7. Конфигурация майнинга (нода)

Параметры, которые можно настроить в `.env` ноды:

```
MINING_DIFFICULTY=4       # Количество ведущих нулей
MAX_TX_PER_BLOCK=100      # Максимум транзакций в блоке
BLOCK_REWARD_ADDRESS=     # Адрес для награды (пусто = нет награды)
```

При изменении difficulty майнерам нужно подстраиваться автоматически — читать `difficulty` из задачи.

---

## 8. Частые проблемы

| Проблема | Решение |
|----------|---------|
| `PoW verification failed` | Убедитесь что timestamp в сабмите **точно совпадает** с timestamp из задачи |
| `Unknown or expired task` | Задача уже обработана (другой майнер нашёл блок быстрее). Возьмите новую задачу |
| `Bad nonce in tx` | Транзакция с невалидным nonce удалена. Ничего не делайте — просто майните следующую задачу |
| Нет транзакций для майнинга | Ждите 3-5 секунд и повторите запрос задачи |
| Всегда одни и те же транзакции в задаче | Если майнер нашёл nonce но не отправил (или отправил с ошибкой), транзакции возвращаются в PENDING и выдаются снова |