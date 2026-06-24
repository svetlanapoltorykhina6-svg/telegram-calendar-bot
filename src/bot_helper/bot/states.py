from aiogram.fsm.state import State, StatesGroup


class ScheduleMeetingStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_email = State()
    waiting_for_description = State()
    waiting_for_confirmation = State()
