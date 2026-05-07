"""
Сервис генерации музыки через Suno API.
Создаёт задачу и поллингом ожидает результата.
"""

import asyncio
import logging

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

INITIAL_DELAY    = 5
POLL_INTERVAL    = 3
MAX_ATTEMPTS     = 60

# Таймаут на один HTTP-запрос к Suno API (секунды)
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

TERMINAL_STATUSES = {"SUCCESS", "failed", "error"}


async def _create_task(session: aiohttp.ClientSession, text: str, style: str = "Pop") -> str:
    payload = {
        "customMode":   True,
        "instrumental": False,
        "model":        settings.MUSIC_MODEL,
        "prompt":       text,
        "style":        style,
        "title":        "AI Song",
    }
    if settings.MUSIC_CALLBACK_URL:
        payload["callBackUrl"] = settings.MUSIC_CALLBACK_URL

    async with session.post(
        f"{settings.MUSIC_API_URL}/generate",
        headers={
            "Authorization": f"Bearer {settings.MUSIC_API_KEY}",
            "Content-Type":  "application/json",
        },
        json=payload,
    ) as resp:
        # content_type=None — не падает если API вернул text/html или другой Content-Type
        data = await resp.json(content_type=None)
        logger.debug("CREATE TASK response: %s", data)

        if data is None:
            raise Exception(f"Suno API вернул пустой ответ при создании задачи [{resp.status}]")

        if resp.status != 200:
            raise Exception(f"Create task failed [{resp.status}]: {data}")

        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise Exception(f"No taskId in response: {data}")

        logger.info("Задача создана: taskId=%s", task_id)
        return task_id


async def _wait_task(session: aiohttp.ClientSession, task_id: str) -> list[str]:
    """Поллинг до получения аудио URL-ов (Suno генерирует 2 варианта)."""
    await asyncio.sleep(INITIAL_DELAY)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with session.get(
                f"{settings.MUSIC_API_URL}/generate/record-info",
                params={"taskId": task_id},
                headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"},
            ) as resp:
                # content_type=None — не падает если API вернул text/html или другой Content-Type
                data = await resp.json(content_type=None)
                logger.debug("POLL [attempt %d/%d]: %s", attempt, MAX_ATTEMPTS, data)

                if data is None:
                    logger.warning(
                        "Пустой ответ от API на поллинге taskId=%s attempt=%d, повтор через %ds",
                        task_id, attempt, POLL_INTERVAL,
                    )
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                if resp.status != 200:
                    raise Exception(f"Poll failed [{resp.status}]: {data}")

                task_data = data.get("data") or {}
                status    = task_data.get("status")
                logger.info("taskId=%s status=%s attempt=%d", task_id, status, attempt)

                if status not in TERMINAL_STATUSES:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                if status == "SUCCESS":
                    songs = (task_data.get("response") or {}).get("sunoData") or []
                    if not songs:
                        raise Exception(f"Status SUCCESS but no sunoData: {data}")

                    urls = [
                        song.get("audioUrl") or song.get("audio_url") or song.get("url")
                        for song in songs
                    ]
                    urls = [u for u in urls if u]

                    if not urls:
                        raise Exception(f"No audio URLs in sunoData: {songs}")

                    logger.info("Музыка готова: %d трека(ов) taskId=%s", len(urls), task_id)
                    return urls

                raise Exception(f"Music generation failed with status={status}: {data}")

        except asyncio.CancelledError:
            logger.warning("Поллинг отменён для taskId=%s", task_id)
            raise
        except Exception:
            raise
        finally:
            pass

    raise TimeoutError(
        f"Music generation timeout after {MAX_ATTEMPTS * POLL_INTERVAL}s (taskId={task_id})"
    )


async def generate_music_from_text(text: str, style: str = "Pop") -> list[str]:
    """
    Создаёт задачу и ждёт результата.
    Возвращает список прямых ссылок на mp3 (обычно 2 варианта).
    """
    async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
        task_id = await _create_task(session, text, style)
        try:
            audio_urls = await _wait_task(session, task_id)
        except Exception:
            logger.error("Ошибка при ожидании результата taskId=%s", task_id)
            raise
        return audio_urls
