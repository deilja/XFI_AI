"""Telegram bot for XFI AI tokens and guarded XFI_CONNECT code changes."""

import asyncio
import os

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

from .code_agent import create_branch_and_commit, generate_edits, analyze_request
from .key_store import create_key

router = Router()
_sessions: dict[int, dict] = {}
_locks: dict[int, asyncio.Lock] = {}


def _admin_ids() -> set[int]:
    raw = os.getenv("XFI_AI_TELEGRAM_ADMIN_IDS", "")
    return {int(item.strip()) for item in raw.split(",") if item.strip().isdigit()}


def _is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in _admin_ids())


def _lock(user_id: int) -> asyncio.Lock:
    return _locks.setdefault(user_id, asyncio.Lock())


def _short(text: str, limit: int = 3500) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…"


@router.message(Command("start"))
async def start(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "XFI AI Bot\n\n"
        "/token — выпустить API-токен XFI AI\n"
        "/code — изменить код XFI_CONNECT обычным текстовым запросом\n"
        "/cancel — отменить текущую задачу\n"
        "/help — показать команды"
    )


@router.message(Command("help"))
async def help_command(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "/token — выпустить токен\n"
        "/code — начать изменение XFI_CONNECT\n"
        "/cancel — отменить задачу\n\n"
        "После /code опишите задачу обычным текстом. Бот задаст уточняющие вопросы,"
        " покажет план и изменения, и только после вашего подтверждения создаст отдельную ветку GitHub."
    )


@router.message(Command("token"))
async def issue_token(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    try:
        rpm = max(1, min(100000, int(os.getenv("XFI_AI_BOT_TOKEN_RPM", "60"))))
        daily = max(1, min(10000000, int(os.getenv("XFI_AI_BOT_TOKEN_DAILY", "5000"))))
    except ValueError:
        rpm, daily = 60, 5000
    token = create_key(name=f"XFI_CONNECT:{message.from_user.id}", rpm_limit=rpm, daily_limit=daily)
    await message.answer(
        "Новый токен XFI AI создан.\n\n"
        f"<code>{token}</code>\n\n"
        "Скопируйте его и добавьте в XFI CONNECT через /ai_token.\n"
        "Токен показывается только сейчас; сохраните его в защищённом месте.",
        parse_mode="HTML",
    )


@router.message(Command("code"))
async def start_code(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    user_id = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    _sessions[user_id] = {"state": "request", "request": args[1].strip() if len(args) > 1 else "", "answers": [], "plan": None}
    if _sessions[user_id]["request"]:
        await _process_request(message)
    else:
        await message.answer("Опишите, что нужно изменить в XFI_CONNECT. Например: «Добавь в админку команду /status, которая показывает состояние VPN-серверов»." )


@router.message(Command("cancel"))
async def cancel(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    _sessions.pop(message.from_user.id, None)
    await message.answer("Текущая задача отменена.")


async def _process_request(message: types.Message) -> None:
    user_id = message.from_user.id
    session = _sessions[user_id]
    async with _lock(user_id):
        await message.answer("Анализирую запрос и структуру XFI_CONNECT…")
        try:
            result = await analyze_request(session["request"], session["answers"])
        except Exception:
            await message.answer("Не удалось проанализировать задачу. Проверьте доступ XFI AI к GitHub и попробуйте снова.")
            return
        if not result.ready:
            session["state"] = "questions"
            session["questions"] = result.questions
            session["question_index"] = 0
            await message.answer("Уточнение:\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(result.questions)))
            return
        session["state"] = "ready"
        session["plan"] = result
        await _generate_and_show(message)


async def _generate_and_show(message: types.Message) -> None:
    user_id = message.from_user.id
    session = _sessions[user_id]
    async with _lock(user_id):
        await message.answer("Требования понятны. Формирую минимальный набор изменений…")
        try:
            patch = await generate_edits(session["request"], session["answers"])
        except Exception:
            await message.answer("Не удалось безопасно сформировать изменения. Задачу не применял.")
            return
        session["patch"] = patch
        files = "\n".join(f"• {e['path']} — {e['reason']}" for e in patch["edits"])
        tests = "\n".join(f"• {x}" for x in patch.get("tests", [])) or "• существующие CI-тесты"
        await message.answer(
            "План готов.\n\n"
            f"{_short(patch['summary'], 1800)}\n\n"
            f"Изменяемые файлы:\n{files}\n\n"
            f"Проверки:\n{tests}\n\n"
            "Код будет записан только в новую ветку GitHub.\n"
            "Для применения напишите: ПОДТВЕРЖДАЮ\n"
            "Для отмены: /cancel"
        )


@router.message()
async def conversational_code(message: types.Message) -> None:
    if not _is_admin(message) or not message.text:
        return
    user_id = message.from_user.id
    session = _sessions.get(user_id)
    if not session:
        return
    text = message.text.strip()
    if session["state"] == "request":
        session["request"] = text
        await _process_request(message)
        return
    if session["state"] == "questions":
        session["answers"].append({"role": "user", "content": text})
        session["question_index"] += 1
        await _process_request(message)
        return
    if session["state"] == "ready" and text.upper() == "ПОДТВЕРЖДАЮ":
        async with _lock(user_id):
            patch = session.get("patch")
            if not patch:
                await message.answer("Нет подготовленных изменений. Начните заново через /code.")
                return
            await message.answer("Подтверждение получено. Создаю отдельную ветку и записываю изменения…")
            try:
                branch, url = await create_branch_and_commit(patch["edits"], f"feat: {patch['summary'][:80]}")
            except Exception:
                await message.answer("Не удалось записать изменения в GitHub. Ветка не считается готовой.")
                return
            _sessions.pop(user_id, None)
            await message.answer(f"Изменения сохранены в ветке {branch}.\n{url}\n\nXFI AI не меняет main напрямую.")
        return
    if session["state"] == "ready":
        await message.answer("Ожидаю «ПОДТВЕРЖДАЮ» или /cancel.")


async def run() -> None:
    token = os.getenv("XFI_AI_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("XFI_AI_TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
