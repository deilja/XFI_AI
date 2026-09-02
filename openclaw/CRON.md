# XFI AI — OpenClaw Cron и эксплуатация

## 10.3. Дополнительный Cron — VPN auto-heal

Запускать от пользователя, под которым работает OpenClaw:

```bash
openclaw cron add \
  --name "vpn-heal" \
  --cron "*/10 * * * *" \
  --session isolated \
  --message "Проверь 3X-UI, xray и другие VPN-панели. Если что-то упало — безопасно перезапусти. Не трогай пользователей, ключи и настройки. Если исправил или не смог поднять — напиши мне в Telegram. Если всё ок — молчи." \
  --announce \
  --channel telegram
```

### Другие полезные задания

Каждый час — более глубокая проверка:

```bash
openclaw cron add --name "hourly-check" --cron "0 * * * *" \
  --message "Сделай полную проверку сервисов и логов VPN-панелей. Исправь простые проблемы, о сложных сообщи." \
  --announce --channel telegram
```

Утренний отчёт:

```bash
openclaw cron add --name "morning-report" --cron "0 9 * * *" \
  --message "Краткий отчёт: что проверял ночью по 3X-UI/xray, были ли проблемы, что исправил." \
  --announce --channel telegram
```

Список заданий:

```bash
openclaw cron list
```

## 11. Полезные команды OpenClaw

| Команда | Назначение |
|---|---|
| `openclaw gateway status` | Статус Gateway |
| `openclaw gateway restart` | Перезапуск Gateway |
| `openclaw models list` | Список моделей |
| `openclaw models set routerai/anthropic/claude-sonnet-4-5` | Сменить модель по умолчанию |
| `openclaw pairing list telegram` | Запросы на доступ |
| `openclaw pairing approve telegram КОД` | Одобрить доступ |
| `openclaw cron list` | Список cron-заданий |
| `openclaw system heartbeat last` | Последний heartbeat |
| `journalctl -u openclaw -f` | Логи в реальном времени |

## 12. Рекомендуемые модели

| Назначение | Модель |
|---|---|
| Основная — код и рассуждения | `routerai/anthropic/claude-sonnet-4-5` |
| Дешёвая / быстрая | `routerai/deepseek/deepseek-chat` или `google/gemini-2.5-flash` |
| Максимально мощная | `routerai/anthropic/claude-opus-4-6` |

Из Telegram:

```text
/model list
/model routerai/anthropic/claude-sonnet-4-5
```

Перед использованием конкретной модели проверьте, что она доступна через настроенного провайдера.

## 13. Быстрая проверка после установки

Напишите боту:

```text
Проверь 3X-UI и xray. Если что-то не работает — попробуй починить и скажи результат
```

или:

```text
Панель не открывается, разберись
```

или:

```text
Что сейчас происходит на сервере
```

Правильный результат: OpenClaw отвечает, может выполнить разрешённую диагностику и при необходимости безопасно перезапустить разрешённый сервис.

## 14. Безопасность

- Telegram использует pairing; неизвестный пользователь не получает доступ без одобрения кода.
- `HEARTBEAT.md` запрещает удаление ключей/пользователей, изменение портов, TLS, Reality, firewall и другие опасные изменения.
- Telegram Bot Token, RouterAI API key и ключи других AI-провайдеров нельзя помещать в Git.
- Ограничивайте Telegram-доступ только доверенными пользователями; при поддержке вашей версии OpenClaw дополнительно используйте `allowFrom` с Telegram user ID.
- Для удалённого VPS-контроля используйте SSH key или SSH agent. Не передавайте SSH-пароли в командной строке.
- Автоматический repair должен быть ограничен allowlist сервисов и не должен менять VPN-конфигурацию.

## 15. Типичные проблемы

| Проблема | Что делать |
|---|---|
| Бот не отвечает | `openclaw gateway status`, затем проверить логи и pairing |
| Модели нет в списке | Проверить API key RouterAI и ID модели |
| Heartbeat молчит | `openclaw system heartbeat last`, проверить `HEARTBEAT.md` |
| Cron не срабатывает | `openclaw cron list`, проверить cron/status команды вашей версии OpenClaw |
| Нет прав на `systemctl` | Запускать Gateway от пользователя с необходимыми правами через заранее настроенный безопасный sudoers allowlist |

## Краткий чеклист установки

1. Обновить систему.
2. Установить OpenClaw.
3. Получить RouterAI API key.
4. Создать Telegram-бота через `@BotFather`.
5. Настроить `~/.openclaw/openclaw.json`.
6. Выполнить `openclaw gateway restart`.
7. Сделать pairing в Telegram.
8. Создать `~/.openclaw/workspace/HEARTBEAT.md`.
9. Включить heartbeat.
10. При необходимости добавить `vpn-heal`, `hourly-check` и `morning-report`.
11. Написать боту тестовую команду и проверить результат.

## Важное ограничение auto-heal

Cron и heartbeat не являются механизмом изменения VPN-конфигурации. Разрешены диагностика и безопасный restart уже существующего сервиса. Не разрешены удаление пользователей/ключей/inbounds, смена портов, TLS/Reality, firewall/DNS/routing, редактирование базы 3X-UI/X-UI и обновление компонентов без отдельного явного решения администратора.
