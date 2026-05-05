import aiohttp

from config import settings

async def generate_music_from_text(text: str) -> bytes:

    """

    Отправляет текст в музыкальный API и возвращает mp3 (bytes)

    """

    async with aiohttp.ClientSession() as session:

        async with session.post(

            settings.MUSIC_API_URL,

            json={"text": text}

        ) as resp:

            if resp.status != 200:

                raise Exception(f"Music API error: {resp.status}")

            return await resp.read()