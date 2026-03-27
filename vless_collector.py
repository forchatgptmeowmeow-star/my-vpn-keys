"""
VLESS Key Collector — async, fast, with validation
"""

import asyncio
import base64
import re
import sys
import time
from urllib.parse import urlparse

try:
    import aiohttp
except ImportError:
    print("Установи зависимость: pip install aiohttp")
    sys.exit(1)

# ──────────────────────────────────────────────
# Источники (публичные GitHub-репозитории)
# ──────────────────────────────────────────────
SOURCES = [
    # VLESS
    "https://raw.githubusercontent.com/EbraSha/free-v2ray-public-list/main/vless.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/splited/vless.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/vless.txt",
    "https://raw.githubusercontent.com/B9424/v2ray-free-configs/main/v2ray.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/splitted/vless.txt",
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/base64/mix",
    "https://raw.githubusercontent.com/mheidari98/.proxy/main/all",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/Long_term_subscription1",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/Long_term_subscription2",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/Long_term_subscription3",
]

OUTPUT_FILE   = "vless_keys.txt"
TIMEOUT_SEC   = 15
MAX_CONCURRENT = 10          # одновременных запросов
VLESS_REGEX   = re.compile(r"vless://[^\s\"'<>\r\n]+")


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def try_decode_base64(text: str) -> str:
    """Пробует декодировать текст из base64. Возвращает оригинал при неудаче."""
    try:
        # Дополняем до кратности 4
        padded = text + "=" * (-len(text) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
        # Если после декодирования есть читаемые строки — возвращаем
        if "vless://" in decoded or "vmess://" in decoded:
            return decoded
    except Exception:
        pass
    return text


def is_valid_vless(key: str) -> bool:
    """Базовая проверка формата vless://UUID@host:port"""
    try:
        # Убираем префикс
        rest = key[len("vless://"):]
        if "@" not in rest:
            return False
        uuid_part, host_part = rest.split("@", 1)
        # UUID ~32 hex символа с дефисами
        if len(uuid_part) < 10:
            return False
        # Должен быть host:port
        if ":" not in host_part.split("?")[0].split("#")[0]:
            return False
        return True
    except Exception:
        return False


def extract_vless_keys(text: str) -> list[str]:
    """Извлекает VLESS-ключи из текста, включая base64-закодированный."""
    # Прямое извлечение
    keys = VLESS_REGEX.findall(text)

    # Попытка base64-декодирования всего текста
    decoded = try_decode_base64(text.strip())
    if decoded != text.strip():
        keys += VLESS_REGEX.findall(decoded)

    # Построчное base64-декодирование
    for line in text.splitlines():
        line = line.strip()
        if line and "vless://" not in line and len(line) > 20:
            decoded_line = try_decode_base64(line)
            if decoded_line != line:
                keys += VLESS_REGEX.findall(decoded_line)

    return keys


# ──────────────────────────────────────────────
# Асинхронный сбор
# ──────────────────────────────────────────────

async def fetch_source(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[str], str | None]:
    """Загружает один источник и возвращает (url, ключи, ошибка)."""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)) as resp:
                if resp.status != 200:
                    return url, [], f"HTTP {resp.status}"
                text = await resp.text(encoding="utf-8", errors="ignore")
                keys = extract_vless_keys(text)
                valid = [k for k in keys if is_valid_vless(k)]
                return url, valid, None
        except asyncio.TimeoutError:
            return url, [], "Таймаут"
        except Exception as e:
            return url, [], str(e)


async def collect_all() -> list[str]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    headers   = {"User-Agent": "Mozilla/5.0 (compatible; VLESSCollector/2.0)"}

    connector = aiohttp.TCPConnector(ssl=False, limit=MAX_CONCURRENT)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        tasks = [fetch_source(session, url, semaphore) for url in SOURCES]

        print(f"{'─'*60}")
        print(f"  Источников: {len(SOURCES)}  |  Параллельно: {MAX_CONCURRENT}")
        print(f"{'─'*60}")

        all_keys: list[str] = []
        for coro in asyncio.as_completed(tasks):
            url, keys, error = await coro
            short = url.split("/")[2]          # только домен для краткости
            if error:
                print(f"  ✗ {short:<35} — {error}")
            else:
                print(f"  ✓ {short:<35} + {len(keys)} ключей")
            all_keys.extend(keys)

    return all_keys


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────

def main() -> None:
    start = time.perf_counter()

    print("\n╔══════════════════════════════════════════════╗")
    print("║        VLESS Key Collector  v2.0             ║")
    print("╚══════════════════════════════════════════════╝\n")

    # Запуск асинхронного сбора
    all_keys = asyncio.run(collect_all())

    # Дедупликация
    unique_keys = sorted(set(all_keys))

    # Сохранение
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(unique_keys))

    elapsed = time.perf_counter() - start

    print(f"\n{'─'*60}")
    print(f"  Всего собрано  : {len(all_keys)}")
    print(f"  Уникальных     : {len(unique_keys)}")
    print(f"  Дублей удалено : {len(all_keys) - len(unique_keys)}")
    print(f"  Время работы   : {elapsed:.2f} сек")
    print(f"  Сохранено в    : {OUTPUT_FILE}")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
