import aiohttp
import asyncio
from config import settings

INITIAL_DELAY = 5
POLL_INTERVAL = 3
MAX_ATTEMPTS  = 60

TERMINAL_STATUSES = {"SUCCESS", "failed", "error"}


async def _create_task(session: aiohttp.ClientSession, text: str, style: str = "Pop") -> str:
    async with session.post(
        f"{settings.MUSIC_API_URL}/generate",
        headers={
            "Authorization": f"Bearer {settings.MUSIC_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "customMode": True,
            "instrumental": False,
            "model": "V4_5ALL",
            "prompt": text,
            "style": style,
            "title": "AI Song",
            "callBackUrl": "https://example.com/callback",
        },
    ) as resp:
        data = await resp.json()
        print("CREATE TASK RESPONSE:", data)

        if resp.status != 200:
            raise Exception(f"Create task failed [{resp.status}]: {data}")

        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise Exception(f"No taskId in response: {data}")

        return task_id


async def _wait_task(session: aiohttp.ClientSession, task_id: str) -> list[str]:
    """Возвращает список audio URL (Suno генерирует 2 варианта)."""
    await asyncio.sleep(INITIAL_DELAY)

    for attempt in range(MAX_ATTEMPTS):
        async with session.get(
            f"{settings.MUSIC_API_URL}/generate/record-info?taskId={task_id}",
            headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"},
        ) as resp:
            data = await resp.json()
            print(f"WAIT RESPONSE [attempt {attempt + 1}]:", data)

            if resp.status != 200:
                raise Exception(f"Poll failed [{resp.status}]: {data}")

            task_data = data.get("data") or {}
            status    = task_data.get("status")
            print("STATUS:", status)

            if status not in TERMINAL_STATUSES:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if status == "SUCCESS":
                songs = (task_data.get("response") or {}).get("sunoData") or []
                if not songs:
                    raise Exception(f"Status SUCCESS but no sunoData: {data}")

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

            raise Exception(f"Music generation failed: {data}")

    raise TimeoutError(f"Music generation timeout after {MAX_ATTEMPTS * POLL_INTERVAL}s")


async def generate_music_from_text(text: str, style: str = "Pop") -> list[str]:
    """
    Создаёт задачу и ждёт результата.
    Возвращает список прямых ссылок на mp3 (обычно 2 варианта).
    """
    async with aiohttp.ClientSession() as session:
        task_id    = await _create_task(session, text, style)
        audio_urls = await _wait_task(session, task_id)
        return audio_urls
