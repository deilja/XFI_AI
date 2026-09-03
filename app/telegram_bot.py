"""Telegram bot for issuing XFI AI Gateway client tokens."""

import os

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from .key_store import create_key

router = Router()


def _admin_ids() -> set[int]:
    raw = os.getenv("XFI_AI_TELEGRAM_ADMIN_IDS", "")
    return {int(item.strip()) for item in raw.split(",") if item.strip().isdigit()}


@router.message(Command("start"))
async def start(message: Message) -> None:
    if message.from_user and message.from_user.id not in _admin_ids():
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "XFI AI Bot\n\n"
        "/token — выпустить новый API-токен XFI AI\n"
        "/help — показать команды"
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    if message.from_user and message.from_user.id not in _admin_ids():
        await message.answer("Доступ запрещён.")
        return
    await message.answer("/token — выпустить новый API-токен XFI AI")


@router.message(Command("token"))
async def issue_token(message: Message) -> None:
    if not message.from_user or message.from_user.id not in _admin_ids():
        await message.answer("Доступ запрещён.")
        return

    token = create_key(
        name=f"XFI_CONNECT:{message.from_user.id}",
        rpm_limit=int(os.getenv("XFI_AI_BOT_TOKEN_RPM", "60")),
        daily_limit=int(os.getenv("XFI_AI_BOT_TOKEN_DAILY", "5000")),
    )
    await message.answer(
        "Новый токен XFI AI создан.\n\n"
        f"<code>{token}</code>\n\n"
        "Скопируйте его и добавьте в XFI CONNECT через команду /ai_token.\n"
        "Токен показывается только сейчас; сохраните его в защищённом месте.",
        parse_mode="HTML",
    )


async def run() -> None:
    token = os.getenv("XFI_AI_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("XFI_AI_TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
