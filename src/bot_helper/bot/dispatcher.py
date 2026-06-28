from __future__ import annotations

from datetime import datetime
import logging

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot_helper.bot.flow import LocalFlowContext, user_uuid_from_telegram_id
from bot_helper.bot.keyboards import (
    admin_request_keyboard,
    confirmation_keyboard,
    dates_keyboard,
    description_keyboard,
    duration_keyboard,
    main_menu_keyboard,
    slots_keyboard,
)
from bot_helper.bot.states import ScheduleMeetingStates
from bot_helper.core.config import Settings
from bot_helper.services.exceptions import ValidationError
from bot_helper.services.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarConfigurationError,
    GoogleCalendarError,
    GoogleCalendarEventCreate,
)
from bot_helper.services.meeting_requests import (
    validate_description,
    validate_email,
    validate_title,
)

logger = logging.getLogger("bot_helper.telegram")


def is_allowed_user(settings: Settings, telegram_id: int | None) -> bool:
    if telegram_id is None:
        return False
    allowed_ids = settings.allowed_telegram_ids or settings.admin_telegram_ids
    if not allowed_ids:
        return False
    return telegram_id in allowed_ids


def is_admin_user(settings: Settings, telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id in settings.admin_telegram_ids


def create_dispatcher(settings: Settings) -> Dispatcher:
    flow_context = LocalFlowContext(settings)
    google_calendar_client = GoogleCalendarClient(settings)
    router = Router(name="base")

    async def ensure_allowed_message(message: Message) -> bool:
        telegram_id = message.from_user.id if message.from_user else None
        if is_allowed_user(settings, telegram_id):
            return True
        logger.warning(
            "telegram user denied",
            extra={
                "event": "telegram_user_denied",
                "component": "telegram",
                "telegram_id": telegram_id,
            },
        )
        await message.answer("Бот приватный. У вас нет доступа.")
        return False

    async def ensure_allowed_callback(callback: CallbackQuery) -> bool:
        telegram_id = callback.from_user.id if callback.from_user else None
        if is_allowed_user(settings, telegram_id):
            return True
        await callback.answer("Нет доступа", show_alert=True)
        return False

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        await state.clear()
        await message.answer(
            "Бот запущен. Выберите действие.",
            reply_markup=main_menu_keyboard(),
        )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        if not await ensure_allowed_message(message):
            return
        await message.answer(
            "Я помогу отправить заявку на встречу. Сейчас доступен тестовый flow: "
            "выбор даты, времени и отправка заявки на согласование."
        )

    @router.message(Command("new"))
    async def new_request_command(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        await state.clear()
        await message.answer(
            "Выберите длительность встречи:",
            reply_markup=duration_keyboard(settings.allowed_meeting_durations),
        )

    @router.message(Command("cancel"))
    async def cancel_command(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        await state.clear()
        await message.answer("Сценарий отменен.", reply_markup=main_menu_keyboard())

    @router.callback_query(F.data == "help")
    async def help_callback(callback: CallbackQuery) -> None:
        if not await ensure_allowed_callback(callback):
            return
        await callback.message.answer(
            "Нажмите «Запланировать встречу», выберите дату и время, затем заполните данные."
        )
        await callback.answer()

    @router.callback_query(F.data == "schedule:start")
    async def schedule_start_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        await state.clear()
        await callback.message.edit_text(
            "Выберите длительность встречи:",
            reply_markup=duration_keyboard(settings.allowed_meeting_durations),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("duration:"))
    async def duration_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        duration_minutes = int(callback.data.split(":", maxsplit=1)[1])
        if duration_minutes not in settings.allowed_meeting_durations:
            await callback.answer("Недоступная длительность встречи.", show_alert=True)
            return
        await state.update_data(duration_minutes=duration_minutes)
        slots = await flow_context.get_slots(duration_minutes)
        if not slots:
            await callback.message.edit_text(
                "Свободных слотов пока нет. Попробуйте позже.",
                reply_markup=main_menu_keyboard(),
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            "Выберите дату. Число в скобках - количество свободных слотов:",
            reply_markup=dates_keyboard(slots),
        )
        await callback.answer()

    @router.callback_query(F.data == "schedule:dates")
    async def dates_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        data = await state.get_data()
        duration_minutes = int(data.get("duration_minutes", settings.meeting_duration_minutes))
        slots = await flow_context.get_slots(duration_minutes)
        await callback.message.edit_text("Выберите дату:", reply_markup=dates_keyboard(slots))
        await callback.answer()

    @router.callback_query(F.data.startswith("date:"))
    async def date_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        data = await state.get_data()
        duration_minutes = int(data.get("duration_minutes", settings.meeting_duration_minutes))
        date_value = callback.data.split(":", maxsplit=1)[1]
        local_date = datetime.fromisoformat(date_value).date()
        slots = await flow_context.get_slots_by_date(local_date, duration_minutes)
        if not slots:
            await callback.message.edit_text(
                "На эту дату свободных слотов уже нет. Выберите другую дату.",
                reply_markup=dates_keyboard(await flow_context.get_slots(duration_minutes)),
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            f"Выберите время на {local_date.strftime('%d.%m.%Y')}:",
            reply_markup=slots_keyboard(slots),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot:"))
    async def slot_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        data = await state.get_data()
        duration_minutes = int(data.get("duration_minutes", settings.meeting_duration_minutes))
        timestamp = int(callback.data.split(":", maxsplit=1)[1])
        slot = await flow_context.get_slot_by_timestamp(timestamp, duration_minutes)
        if slot is None:
            await callback.message.edit_text(
                "Этот слот больше недоступен. Выберите другое время.",
                reply_markup=dates_keyboard(await flow_context.get_slots(duration_minutes)),
            )
            await callback.answer()
            return
        await state.update_data(
            duration_minutes=duration_minutes,
            start_at=slot.start_at.isoformat(),
            end_at=slot.end_at.isoformat(),
            local_date=slot.local_date.strftime("%d.%m.%Y"),
            local_start=slot.local_start_time.strftime("%H:%M"),
            local_end=slot.local_end_time.strftime("%H:%M"),
        )
        await state.set_state(ScheduleMeetingStates.waiting_for_title)
        await callback.message.edit_text("Введите тему встречи. Например: «Обсудить проект».")
        await callback.answer()

    @router.message(ScheduleMeetingStates.waiting_for_title)
    async def title_message(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        try:
            title = validate_title(message.text or "")
        except ValidationError:
            await message.answer("Тема должна быть от 3 до 120 символов. Введите еще раз.")
            return
        await state.update_data(title=title)
        await state.set_state(ScheduleMeetingStates.waiting_for_email)
        await message.answer("Введите email, на который нужно отправить приглашение.")

    @router.message(ScheduleMeetingStates.waiting_for_email)
    async def email_message(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        try:
            email = validate_email(message.text or "")
        except ValidationError:
            await message.answer("Email выглядит некорректно. Введите email еще раз.")
            return
        await state.update_data(email=email)
        await state.set_state(ScheduleMeetingStates.waiting_for_description)
        await message.answer(
            "Введите описание встречи или нажмите «Пропустить».",
            reply_markup=description_keyboard(),
        )

    @router.callback_query(F.data == "description:skip")
    async def skip_description_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        await state.update_data(description=None)
        await show_confirmation(callback.message, state)
        await callback.answer()

    @router.message(ScheduleMeetingStates.waiting_for_description)
    async def description_message(message: Message, state: FSMContext) -> None:
        if not await ensure_allowed_message(message):
            return
        try:
            description = validate_description(message.text)
        except ValidationError:
            await message.answer("Описание слишком длинное. Максимум 2000 символов.")
            return
        await state.update_data(description=description)
        await show_confirmation(message, state)

    async def show_confirmation(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        await state.set_state(ScheduleMeetingStates.waiting_for_confirmation)
        description = data.get("description") or "не указано"
        await message.answer(
            "Проверьте заявку:\n\n"
            f"Дата: {data['local_date']}\n"
            f"Время: {data['local_start']}–{data['local_end']}\n"
            f"Длительность: {data['duration_minutes']} минут\n"
            f"Тема: {data['title']}\n"
            f"Email: {data['email']}\n"
            f"Описание: {description}",
            reply_markup=confirmation_keyboard(),
        )

    @router.callback_query(F.data == "request:confirm")
    async def confirm_request_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        data = await state.get_data()
        telegram_id = callback.from_user.id
        start_at = datetime.fromisoformat(data["start_at"])
        duration_minutes = int(data.get("duration_minutes", settings.meeting_duration_minutes))
        slot = await flow_context.get_slot_by_timestamp(
            int(start_at.timestamp()),
            duration_minutes,
        )
        if slot is None:
            await state.clear()
            await callback.message.edit_text(
                "Слот больше недоступен. Начните запись заново.",
                reply_markup=main_menu_keyboard(),
            )
            await callback.answer()
            return
        hold_key = await flow_context.hold_slot(slot.interval)
        request_data = {
            "telegram_id": telegram_id,
            "client_telegram_id": telegram_id,
            "user_id": str(user_uuid_from_telegram_id(telegram_id)),
            "title": data["title"],
            "email": data["email"],
            "description": data.get("description"),
            "start_at": data["start_at"],
            "end_at": data["end_at"],
            "duration_minutes": duration_minutes,
            "local_date": data["local_date"],
            "local_start": data["local_start"],
            "local_end": data["local_end"],
            "hold_key": hold_key,
            "status": "pending",
        }
        stored_request = flow_context.add_request(request_data)
        await state.clear()
        await callback.message.edit_text(
            "Заявка отправлена на согласование. Я сообщу, когда встреча будет подтверждена.",
            reply_markup=main_menu_keyboard(),
        )
        await notify_admins(callback, settings, stored_request)
        await callback.answer()

    async def notify_admins(
        callback: CallbackQuery,
        settings: Settings,
        request_data: dict[str, object],
    ) -> None:
        text = (
            "Новая заявка на встречу:\n\n"
            f"ID: {request_data['request_id']}\n"
            f"Дата: {request_data['local_date']}\n"
            f"Время: {request_data['local_start']}–{request_data['local_end']}\n"
            f"Длительность: {request_data['duration_minutes']} минут\n"
            f"Тема: {request_data['title']}\n"
            f"Email: {request_data['email']}\n"
            "Выберите действие:"
        )
        for admin_id in settings.admin_telegram_ids:
            try:
                await callback.bot.send_message(
                    admin_id,
                    text,
                    reply_markup=admin_request_keyboard(str(request_data["request_id"])),
                )
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "admin notification failed",
                    extra={
                        "event": "admin_notification_failed",
                        "component": "telegram",
                        "telegram_id": admin_id,
                        "error_code": exc.__class__.__name__,
                    },
                )

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def approve_request_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(settings, callback.from_user.id if callback.from_user else None):
            await callback.answer("Только администратор может согласовывать заявки.", show_alert=True)
            return

        request_id = callback.data.rsplit(":", maxsplit=1)[1]
        request_data = flow_context.get_request(request_id)
        if request_data is None:
            await callback.answer("Заявка не найдена. Возможно, бот был перезапущен.", show_alert=True)
            return
        if request_data.get("status") != "pending":
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            return

        flow_context.update_request(request_id, status="approving")
        try:
            result = await google_calendar_client.create_event(
                GoogleCalendarEventCreate(
                    request_id=request_id,
                    title=str(request_data["title"]),
                    description=_build_calendar_description(request_data),
                    start_at=datetime.fromisoformat(str(request_data["start_at"])),
                    end_at=datetime.fromisoformat(str(request_data["end_at"])),
                    attendee_email=str(request_data["email"]),
                    timezone=settings.default_timezone,
                    enable_google_meet=settings.enable_google_meet,
                )
            )
        except GoogleCalendarConfigurationError as exc:
            flow_context.update_request(request_id, status="pending")
            await callback.answer("Не хватает настроек Google Calendar.", show_alert=True)
            await callback.message.answer(
                "Не удалось согласовать заявку: не настроена интеграция с Google Calendar.\n\n"
                f"{exc}\n\n"
                "После настройки .env нажмите «Согласовать» еще раз.",
                reply_markup=admin_request_keyboard(request_id),
            )
            return
        except GoogleCalendarError as exc:
            flow_context.update_request(request_id, status="pending")
            await callback.answer("Google Calendar вернул ошибку.", show_alert=True)
            await callback.message.answer(
                "Не удалось создать событие в Google Calendar.\n\n"
                f"{exc}\n\n"
                "Заявка оставлена в ожидании, можно повторить согласование после исправления настроек.",
                reply_markup=admin_request_keyboard(request_id),
            )
            return
        except Exception as exc:  # pragma: no cover
            flow_context.update_request(request_id, status="pending")
            logger.exception(
                "request approval failed",
                extra={
                    "event": "request_approval_failed",
                    "component": "telegram",
                    "request_id": request_id,
                    "error_code": exc.__class__.__name__,
                },
            )
            await callback.answer("Не удалось согласовать заявку.", show_alert=True)
            await callback.message.answer(
                "Не удалось согласовать заявку из-за внутренней ошибки.\n\n"
                "Заявка оставлена в ожидании, можно повторить согласование после исправления.",
                reply_markup=admin_request_keyboard(request_id),
            )
            return

        flow_context.update_request(
            request_id,
            status="approved",
            google_event_id=result.event_id,
            google_event_link=result.html_link,
            google_meet_link=result.meet_link,
        )
        calendar_status = (
            f"Google Meet: {result.meet_link}"
            if result.meet_link
            else "Google Meet: ссылка не получена от Google Calendar"
        )
        attendee_status = (
            "Email-приглашение отправлено."
            if result.attendee_invited
            else "Email-приглашение не отправлено."
        )
        await callback.message.edit_text(
            "Заявка согласована.\n\n"
            f"Дата: {request_data['local_date']}\n"
            f"Время: {request_data['local_start']}–{request_data['local_end']}\n"
            f"Длительность: {request_data['duration_minutes']} минут\n"
            f"Тема: {request_data['title']}\n"
            f"Email: {request_data['email']}\n"
            f"{calendar_status}\n"
            f"{attendee_status}"
        )
        await callback.bot.send_message(
            int(request_data["client_telegram_id"]),
            "Встреча подтверждена.\n\n"
            f"Дата: {request_data['local_date']}\n"
            f"Время: {request_data['local_start']}–{request_data['local_end']}\n"
            f"Длительность: {request_data['duration_minutes']} минут\n"
            f"Тема: {request_data['title']}\n"
            f"{calendar_status}\n"
            f"{attendee_status}",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Заявка согласована.")

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def reject_request_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(settings, callback.from_user.id if callback.from_user else None):
            await callback.answer("Только администратор может отклонять заявки.", show_alert=True)
            return

        request_id = callback.data.rsplit(":", maxsplit=1)[1]
        request_data = flow_context.get_request(request_id)
        if request_data is None:
            await callback.answer("Заявка не найдена. Возможно, бот был перезапущен.", show_alert=True)
            return
        if request_data.get("status") != "pending":
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            return

        flow_context.update_request(request_id, status="rejected")
        await callback.message.edit_text(
            "Заявка отклонена.\n\n"
            f"Дата: {request_data['local_date']}\n"
            f"Время: {request_data['local_start']}–{request_data['local_end']}\n"
            f"Длительность: {request_data['duration_minutes']} минут\n"
            f"Тема: {request_data['title']}\n"
            f"Email: {request_data['email']}"
        )
        await callback.bot.send_message(
            int(request_data["client_telegram_id"]),
            "Заявка на встречу отклонена.\n\n"
            f"Дата: {request_data['local_date']}\n"
            f"Время: {request_data['local_start']}–{request_data['local_end']}\n"
            f"Длительность: {request_data['duration_minutes']} минут\n"
            f"Тема: {request_data['title']}",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Заявка отклонена.")

    def _build_calendar_description(request_data: dict[str, object]) -> str:
        parts = [
            str(request_data.get("description") or "Описание не указано."),
            "",
            "Создано через Telegram-бот.",
            f"Email клиента: {request_data['email']}",
            f"Telegram user ID: {request_data['client_telegram_id']}",
            f"Request ID: {request_data['request_id']}",
        ]
        return "\n".join(parts)

    @router.callback_query(F.data == "flow:cancel")
    async def flow_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_allowed_callback(callback):
            return
        await state.clear()
        await callback.message.edit_text("Сценарий отменен.", reply_markup=main_menu_keyboard())
        await callback.answer()

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    return dispatcher
