"""
Сервис генерации музыки через Suno API.
"""

import logging
import asyncio
import aiohttp
from config import settings

logger = logging.getLogger(__name__)

INITIAL_DELAY  = 10   # Suno обычно стартует не раньше 10 сек
POLL_INTERVAL  = 5    # опрашиваем каждые 5 сек
MAX_ATTEMPTS   = 48   # 48 * 5 = 240 сек (4 минуты)

TERMINAL_STATUSES = {"SUCCESS", "failed", "error"}


async def _create_task(session: aiohttp.ClientSession, text: str, style: str = "Pop") -> str:
    callback_url = settings.MUSIC_CALLBACK_URL or ""

    payload = {
        "customMode":   True,
        "instrumental": False,
        "model":        settings.MUSIC_MODEL,
        "prompt":       text,
        "style":        style,
        "title":        "AI Song",
    }
    if callback_url:
        payload["callBackUrl"] = callback_url

    async with session.post(
        f"{settings.MUSIC_API_URL}/generate",
        headers={
            "Authorization": f"Bearer {settings.MUSIC_API_KEY}",
            "Content-Type":  "application/json",
        },
        json=payload,
    ) as resp:
        raw = await resp.text()
        logger.info("CREATE TASK raw response [%d]: %s", resp.status, raw)

        try:
            data = await resp.json(content_type=None)
        except Exception as e:
            raise Exception(f"Failed to parse create task JSON: {e} | raw: {raw}")

        if resp.status != 200:
            raise Exception(f"Create task failed [{resp.status}]: {data}")

        # Пробуем оба варианта структуры ответа
        task_id = (
            (data.get("data") or {}).get("taskId")
            or data.get("taskId")
        )
        if not task_id:
            raise Exception(f"No taskId in response: {data}")

        logger.info("Task created: taskId=%s", task_id)
        return task_id


async def _wait_task(session: aiohttp.ClientSession, task_id: str) -> list[str]:
    """Возвращает список audio URL (Suno генерирует 2 варианта)."""
    await asyncio.sleep(INITIAL_DELAY)

    for attempt in range(MAX_ATTEMPTS):
        async with session.get(
            f"{settings.MUSIC_API_URL}/generate/record-info",
            params={"taskId": task_id},
            headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"},
        ) as resp:
            raw = await resp.text()
            logger.info("POLL raw response [attempt %d, status %d]: %s", attempt + 1, resp.status, raw)

            try:
                data = await resp.json(content_type=None)
            except Exception as e:
                raise Exception(f"Failed to parse poll JSON: {e} | raw: {raw}")

            if resp.status != 200:
                raise Exception(f"Poll failed [{resp.status}]: {data}")

            # Защищаемся от None на каждом уровне
            task_data = data.get("data") or {}
            status    = task_data.get("status")
            logger.info("Music task status: %s", status)

            if status not in TERMINAL_STATUSES:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if status == "SUCCESS":
                response_block = task_data.get("response") or {}
                songs = response_block.get("sunoData") or []

                # Некоторые версии API кладут треки напрямую в data
                if not songs:
                    songs = task_data.get("sunoData") or []

                if not songs:
                    raise Exception(f"Status SUCCESS but no sunoData found: {data}")

                urls = []
                for song in songs:
                    url = (
                        song.get("audioUrl")
                        or song.get("audio_url")
                        or song.get("url")
                    )
                    if url:
                        urls.append(url)

                if not urls:
                    raise Exception(f"No audio URLs in sunoData: {songs}")

                return urls

            raise Exception(f"Music generation failed with status '{status}': {data}")

    raise TimeoutError(
        f"Music generation timeout after {MAX_ATTEMPTS * POLL_INTERVAL}s"
    )


async def generate_music_from_text(text: str, style: str = "Pop") -> list[str]:
    """
    Создаёт задачу и ждёт результата.
    Возвращает список прямых ссылок на mp3 (обычно 2 варианта).
    """
    # connect_timeout — на установку соединения (30 сек)
    # total=None — не ограничиваем общее время сессии, polling сам управляет длительностью
    timeout = aiohttp.ClientTimeout(connect=30, total=None)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        task_id    = await _create_task(session, text, style)
        audio_urls = await _wait_task(session, task_id)
        return audio_urls
