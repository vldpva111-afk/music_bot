# 🎵 Music Gift Bot

Telegram-бот для генерации персонализированных песен с помощью OpenAI GPT-4o.

## Структура проекта

```
bot/
├── main.py                  # Точка входа
├── config.py                # Конфиг (чтение .env)
├── requirements.txt
├── .env.example
├── handlers/
│   ├── __init__.py
│   ├── start.py             # /start и кнопка "Создать песню"
│   ├── genre.py             # Выбор жанра
│   ├── mood.py              # Выбор настроения
│   ├── voice.py             # Выбор голоса
│   ├── details.py           # Ввод деталей + генерация
│   └── editing.py           # Внесение правок
├── keyboards/
│   ├── __init__.py
│   └── keyboards.py         # Все клавиатуры
├── states/
│   ├── __init__.py
│   └── song_states.py       # FSM состояния
└── services/
    ├── __init__.py
    └── openai_service.py    # Работа с OpenAI API
```

## Установка и запуск

### 1. Клонируй репозиторий и перейди в папку

```bash
cd music_bot
```

### 2. Создай виртуальное окружение

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Установи зависимости

```bash
pip install -r requirements.txt
```

### 4. Создай файл `.env`

```bash
cp .env.example .env
```

Заполни значения:
```
BOT_TOKEN=твой_токен_от_BotFather
OPENAI_API_KEY=твой_ключ_OpenAI
```

### 5. Запусти бота

```bash
python main.py
```

## FSM состояния

| Состояние | Описание |
|-----------|----------|
| `start` | Приветствие, ожидание нажатия "Создать песню" |
| `genre` | Выбор жанра |
| `mood` | Выбор настроения |
| `voice` | Выбор голоса |
| `details` | Ввод деталей о человеке |
| `editing` | Просмотр результата / внесение правок |

## Получение токенов

- **BOT_TOKEN**: создай бота через [@BotFather](https://t.me/BotFather) в Telegram
- **OPENAI_API_KEY**: получи на [platform.openai.com](https://platform.openai.com/api-keys)
