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
        "title":        "Your Song",  # только латиница — Suno API не принимает кириллицу в title
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

        task_id = (
            (data.get("data") or {}).get("taskId")
            or data.get("taskId")
        )
        if not task_id:
            raise Exception(f"No taskId in response: {data}")

        logger.info("Task created: taskId=%s", task_id)
        return task_id


async def _download_audio(session: aiohttp.ClientSession, url: str) -> bytes:
    """Скачивает аудио по URL и возвращает байты."""
    logger.info("Downloading audio from: %s", url)
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"Failed to download audio [{resp.status}] from {url}")
        data = await resp.read()
        logger.info("Downloaded %d bytes from %s", len(data), url)
        return data


async def _wait_task(session: aiohttp.ClientSession, task_id: str) -> list[bytes]:
    """
    Ждёт завершения задачи и возвращает список аудио в виде байтов.
    Suno генерирует 2 варианта.
    """
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

            task_data = data.get("data") or {}
            status    = task_data.get("status")
            logger.info("Music task status: %s", status)

            # Любой fail-статус ловим СРАЗУ — не ждём 4 минуты до timeout.
            # Suno возвращает разные варианты: GENERATE_AUDIO_FAILED,
            # CREATE_TASK_FAILED, CALLBACK_EXCEPTION, SENSITIVE_WORD_ERROR и т.п.
            # Ловим по подстроке, чтобы быть устойчивыми к новым типам ошибок.
            status_upper = status.upper() if status else ""
            if any(kw in status_upper for kw in ("FAIL", "ERROR", "EXCEPTION")):
                err_msg = task_data.get("errorMessage") or "unknown"
                err_code = task_data.get("errorCode")
                raise Exception(
                    f"Music generation failed [{status}, code={err_code}]: {err_msg}"
                )

            # failed / error (lowercase, на всякий случай — старый формат)
            if status in {"failed", "error"}:
                raise Exception(f"Music generation failed with status '{status}': {data}")

            # PENDING и другие промежуточные — ждём
            if status not in TERMINAL_STATUSES and status != "TEXT_SUCCESS":
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # SUCCESS или TEXT_SUCCESS — ищем лучший доступный URL
            response_block = task_data.get("response") or {}
            songs = response_block.get("sunoData") or task_data.get("sunoData") or []

            urls = []
            for song in songs:
                # Приоритет: прямой audioUrl → streamAudioUrl (проксированный) → source* варианты
                url = (
                    song.get("audioUrl")
                    or song.get("audio_url")
                    or song.get("streamAudioUrl")
                    or song.get("sourceStreamAudioUrl")
                    or song.get("url")
                )
                if url:
                    urls.append(url)

            if not urls:
                logger.info("Status '%s' but no audio URLs yet, waiting...", status)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            logger.info("Got %d audio URLs at status '%s', downloading...", len(urls), status)

            # Скачиваем все треки параллельно
            audio_bytes_list = await asyncio.gather(
                *[_download_audio(session, url) for url in urls],
                return_exceptions=True,
            )

            result = []
            for i, item in enumerate(audio_bytes_list):
                if isinstance(item, Exception):
                    logger.warning("Failed to download track %d: %s", i + 1, item)
                else:
                    result.append(item)

            if result:
                logger.info("Successfully downloaded %d/%d tracks", len(result), len(urls))
                return result

            # Все загрузки упали — ждём ещё (аудио ещё рендерится)
            logger.warning("All downloads failed, waiting for audio to become ready...")
            await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Music generation timeout after {MAX_ATTEMPTS * POLL_INTERVAL}s")


async def generate_music_from_text(text: str, style: str = "Pop") -> list[bytes]:
    """
    Создаёт задачу, ждёт результата и скачивает аудио.
    Возвращает список байтов аудиофайлов (обычно 2 варианта).
    """
    timeout = aiohttp.ClientTimeout(connect=30, total=None)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        task_id     = await _create_task(session, text, style)
        audio_bytes = await _wait_task(session, task_id)
        return audio_bytes
