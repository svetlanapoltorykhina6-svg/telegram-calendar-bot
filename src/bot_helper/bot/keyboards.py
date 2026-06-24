from __future__ import annotations

from collections import defaultdict
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot_helper.services.availability import AvailableSlot

WEEKDAY_LABELS = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Запланировать встречу", callback_data="schedule:start")
    builder.button(text="Помощь", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()


def duration_keyboard(duration_minutes: int | list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    durations = duration_minutes if isinstance(duration_minutes, list) else [duration_minutes]
    for duration in durations:
        builder.button(text=format_duration(duration), callback_data=f"duration:{duration}")
    builder.button(text="Отмена", callback_data="flow:cancel")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def format_duration(duration_minutes: int) -> str:
    if duration_minutes < 60:
        return f"{duration_minutes} минут"
    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    if minutes == 0:
        return f"{hours} час"
    return f"{hours} час {minutes} минут"


def dates_keyboard(slots: list[AvailableSlot], limit: int = 10) -> InlineKeyboardMarkup:
    dates: dict[date, int] = defaultdict(int)
    for slot in slots:
        dates[slot.local_date] += 1

    builder = InlineKeyboardBuilder()
    for local_date in list(sorted(dates))[:limit]:
        label = (
            f"{WEEKDAY_LABELS[local_date.isoweekday()]}, "
            f"{local_date.strftime('%d.%m')} ({dates[local_date]})"
        )
        builder.button(text=label, callback_data=f"date:{local_date.isoformat()}")

    builder.button(text="Отмена", callback_data="flow:cancel")
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def slots_keyboard(slots: list[AvailableSlot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in slots:
        timestamp = int(slot.start_at.timestamp())
        builder.button(text=slot.local_start_time.strftime("%H:%M"), callback_data=f"slot:{timestamp}")

    builder.button(text="Назад к датам", callback_data="schedule:dates")
    builder.button(text="Отмена", callback_data="flow:cancel")
    builder.adjust(3)
    return builder.as_markup()


def description_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="description:skip")],
            [InlineKeyboardButton(text="Отмена", callback_data="flow:cancel")],
        ]
    )


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить заявку", callback_data="request:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="flow:cancel")],
        ]
    )


def admin_request_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Согласовать",
                    callback_data=f"admin:approve:{request_id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"admin:reject:{request_id}",
                ),
            ]
        ]
    )
