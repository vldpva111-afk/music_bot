import aiohttp

import asyncio

from config import settings

# 1. создать задачу

async def _create_task(session, text: str):

    async with session.post(

        f"{settings.MUSIC_API_URL}/generate",

        headers={

            "Authorization": f"Bearer {settings.MUSIC_API_KEY}",

            "Content-Type": "application/json"

        },

        json={

            "customMode": False,

            "instrumental": False,

            "model": "V5_5",

            "prompt": text

        }

    ) as resp:

        data = await resp.json()

        if resp.status != 200:

            raise Exception(data)

        return data["data"]["taskId"]

# 2. ждать результат (URL)

async def _wait_task(session, task_id: str):

    for _ in range(60):

        async with session.get(

            f"{settings.MUSIC_API_URL}/details/{task_id}",

            headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"}

        ) as resp:

            data = await resp.json()

            if resp.status != 200:

                raise Exception(data)

            if data["data"]["status"] == "complete":

                return data["data"]["songs"][0]["audioUrl"]

        await asyncio.sleep(3)

    raise TimeoutError("Music generation timeout")

# 3. скачать mp3

async def download_audio(session, url: str):

    async with session.get(url) as resp:

        if resp.status != 200:

            raise Exception(f"Download error: {resp.status}")

        return await resp.read()

# 🔥 ГЛАВНАЯ ФУНКЦИЯ

async def generate_music_from_text(text: str):

    async with aiohttp.ClientSession() as session:

        task_id = await _create_task(session, text)

        audio_url = await _wait_task(session, task_id)

        audio_bytes = await download_audio(session, audio_url)

        return audio_bytes