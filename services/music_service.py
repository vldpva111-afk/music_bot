import aiohttp
import asyncio
from config import settings

INITIAL_DELAY = 5       # секунд перед первым поллингом
POLL_INTERVAL = 3       # секунд между запросами
MAX_ATTEMPTS  = 60      # 60 × 3s = 3 минуты максимум

TERMINAL_STATUSES = {"complete", "failed", "error"}


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
            "style": style,        # ← теперь параметр, не константа
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


async def _wait_task(session: aiohttp.ClientSession, task_id: str) -> str:
    await asyncio.sleep(INITIAL_DELAY)  # задача только создана — дать время API

    for attempt in range(MAX_ATTEMPTS):
        async with session.get(
            f"{settings.MUSIC_API_URL}/details/{task_id}",
            headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"},
        ) as resp:
            data = await resp.json()
            print(f"WAIT RESPONSE [attempt {attempt + 1}]:", data)

            if resp.status != 200:
                raise Exception(f"Poll failed [{resp.status}]: {data}")

            task_data = data.get("data") or {}
            status = task_data.get("status")
            print("STATUS:", status)

            if status not in TERMINAL_STATUSES:
                # pending / processing / queued — продолжаем ждать
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if status == "complete":
                songs = task_data.get("songs") or []
                if not songs:
                    raise Exception(f"Status complete but no songs: {data}")

                song = songs[0]
                audio_url = (
                    song.get("audioUrl")
                    or song.get("audio_url")
                    or song.get("url")
                )
                if not audio_url:
                    raise Exception(f"No audio URL in song object: {song}")

                return audio_url

            # status == "failed" или "error"
            raise Exception(f"Music generation failed: {data}")

    raise TimeoutError(f"Music generation timeout after {MAX_ATTEMPTS * POLL_INTERVAL}s")