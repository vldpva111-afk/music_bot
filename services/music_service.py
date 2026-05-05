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

            "customMode": True,

            "instrumental": False,

            "model": "V4_5ALL",

            "prompt": text,              # текст песни

            "style": "Pop",              # стиль (пока фикс)

            "title": "AI Song",          # название

            "callBackUrl": "https://example.com/callback"

        }

    ) as resp:

        data = await resp.json()

        print("CREATE TASK RESPONSE:", data)  # 👈 оставь для дебага

        if resp.status != 200:

            raise Exception(data)

        if not data.get("data"):

            raise Exception(f"Invalid response: {data}")

        return data["data"]["taskId"]

# 2. ждать результат (URL)

async def _wait_task(session, task_id: str):

    for _ in range(60):

        async with session.get(

            f"{settings.MUSIC_API_URL}/details/{task_id}",

            headers={"Authorization": f"Bearer {settings.MUSIC_API_KEY}"}

        ) as resp:

            data = await resp.json()

            print("WAIT RESPONSE:", data)  # 👈 лог

            if resp.status != 200:

                raise Exception(data)

            if not data.get("data"):

                continue  # просто ждём дальше

            status = data["data"].get("status")
            if status == "failed":

                raise Exception(f"Music generation failed: {data}")

            if status == "complete":

                songs = data["data"].get("songs")

                if not songs:

                    raise Exception(f"No songs in response: {data}")

                song = songs[0]

                # 🔥 ловим разные варианты ключей

                audio_url = (

                    song.get("audioUrl")

                    or song.get("audio_url")

                    or song.get("url")

                )

                if not audio_url:

                    raise Exception(f"No audio url in song: {song}")

                return audio_url

        await asyncio.sleep(3)

    raise TimeoutError("Music generation timeout")