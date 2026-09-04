"""Telegram control plane for independently installed XFI projects."""

import asyncio
import json
import os

import httpx
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

from .key_store import create_key
from .project_editor import PROJECTS, analyze, apply_edits_async, generate_edits

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


def _usage() -> str:
    return (
        "/token — выпустить API-токен XFI AI\n"
        "/code connect <задача> — изменить установленный XFI_CONNECT\n"
        "/code webapp <задача> — изменить установленный XFI_3XUI_WebApp\n"
        "/cancel — отменить текущую задачу\n"
        "/help — показать команды"
    )


@router.message(Command("start"))
async def start(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    await message.answer("XFI AI Control Plane\n\n" + _usage())


@router.message(Command("help"))
async def help_command(message: types.Message) -> None:
    if not _is_admin(message):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        _usage()
        + "\n\nXFI_CONNECT и XFI_3XUI_WebApp — независимые проекты. XFI AI выбирает один установленный проект и работает только с ним."
        + "\n\nПосле /code <project> задача анализируется локально, затем AI готовит изменения. После «ПОДТВЕРЖДАЮ» создаётся backup, проверяется stale SHA, выполняется валидация, перезапуск и health-check. При ошибке — rollback. GitHub для runtime-изменений не используется."
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
    token = create_key(name=f"XFI_AI:{message.from_user.id}", rpm_limit=rpm, daily_limit=daily)
    await message.answer(
        "Новый токен XFI AI создан.\n\n"
        f"<code>{token}</code>\n\n"
        "Токен показывается только сейчас; сохраните его в защищённом месте.",
        parse_mode="HTML",
    )


@router.message(Command("code"))
async def start_code(message: types.Message) -> None:
    if not _is_admin(message):
        return
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 2 or args[1].lower() not in PROJECTS:
        await message.answer("Укажите проект: /code connect <задача> или /code webapp <задача>")
        return
    project = args[1].lower()
    request = args[2].strip() if len(args) > 2 else ""
    user_id = message.from_user.id
    _sessions[user_id] = {"state": "request", "project": project, "request": request, "answers": [], "plan": None}
    if request:
        await _process_request(message)
    else:
        await message.answer(f"Опишите задачу для {PROJECTS[project]['name']} обычным текстом.")


@router.message(Command("cancel"))
async def cancel(message: types.Message) -> None:
    if not _is_admin(message):
        return
    _sessions.pop(message.from_user.id, None)
    await message.answer("Текущая задача отменена.")


async def _process_request(message: types.Message) -> None:
    user_id = message.from_user.id
    session = _sessions.get(user_id)
    if not session:
        return
    async with _lock(user_id):
        project = session["project"]
        await message.answer(f"Анализирую установленный {PROJECTS[project]['name']}…")
        try:
            result = await analyze(project, session["request"], session["answers"])
        except (RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError, httpx.HTTPError) as exc:
            await message.answer(f"Не удалось проанализировать проект: {type(exc).__name__}: {exc}")
            return
        if not result["ready"]:
            session["state"] = "questions"
            session["questions"] = result["questions"]
            session["question_index"] = 0
            if not result["questions"]:
                await message.answer("Не хватает требований. Уточните задачу более конкретно.")
                return
            await message.answer(f"Уточняющий вопрос:\n{result['questions'][0]}")
            return
        session["state"] = "ready"
        session["plan"] = result
    await _generate_and_show(message)


async def _generate_and_show(message: types.Message) -> None:
    user_id = message.from_user.id
    session = _sessions.get(user_id)
    if not session:
        return
    async with _lock(user_id):
        await message.answer("Требования понятны. Формирую изменения для установленной версии…")
        try:
            patch = await generate_edits(session["project"], session["request"], session["answers"])
        except (RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError, httpx.HTTPError) as exc:
            await message.answer(f"Не удалось безопасно сформировать изменения: {type(exc).__name__}: {exc}")
            return
        session["patch"] = patch
        files = "\n".join(f"• {e['path']} — {e['reason']}" for e in patch["edits"])
        tests = "\n".join(f"• {x}" for x in patch.get("tests", [])) or "• project-specific validation + service health-check"
        await message.answer(
            "План готов.\n\n"
            f"{_short(patch['summary'], 1800)}\n\n"
            f"Проект: {PROJECTS[session['project']]['name']}\n"
            f"Изменяемые файлы:\n{files}\n\n"
            f"Проверки:\n{tests}\n\n"
            "После подтверждения изменения будут внесены НЕ в GitHub, а непосредственно в выбранный установленный проект.\n"
            "Backup создаётся автоматически.\n"
            "Для применения напишите: ПОДТВЕРЖДАЮ\nДля отмены: /cancel"
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
        index = session.get("question_index", 0)
        questions = session.get("questions", [])
        question = questions[index] if index < len(questions) else ""
        if question:
            session["answers"].append({"role": "assistant", "content": question})
        session["answers"].append({"role": "user", "content": text})
        session["question_index"] = index + 1
        await _process_request(message)
        return
    if session["state"] == "ready" and text.upper() in {"ПОДТВЕРЖДАЮ", "ПОДТВЕРЖДАЮ!", "ДА"}:
        async with _lock(user_id):
            patch = session.get("patch")
            if not patch:
                await message.answer("Нет подготовленных изменений. Начните заново через /code.")
                return
            name = PROJECTS[session["project"]]["name"]
            await message.answer(f"Подтверждение получено. Создаю backup и применяю изменения непосредственно к {name}…")
            try:
                result = await apply_edits_async(session["project"], patch["edits"], restart=True)
            except Exception as exc:
                await message.answer(f"❌ Изменение НЕ прошло проверку. Выполнен автоматический rollback.\nОшибка: {type(exc).__name__}: {exc}")
                _sessions.pop(user_id, None)
                return
            _sessions.pop(user_id, None)
            await message.answer(
                f"✅ {name} обновлён напрямую.\n\n"
                f"Файлы: {', '.join(result['changed'])}\n"
                f"Backup: {result['backup']}\n"
                f"Служба: {result['service']} — active\n\n"
                "XFI_CONNECT и XFI_3XUI_WebApp не зависят друг от друга. GitHub не использовался."
            )
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
