from vk_api.keyboard import VkKeyboard, VkKeyboardColor

BUTTON_PARTNERS = "🚗 Партнёры и скидки"
BUTTON_MY_CODES = "🎟 Мои коды"
BUTTON_SUBSCRIPTION = "💳 Подписка"
BUTTON_HELP = "❓ Помощь"
BUTTON_BACK = "⬅️ Назад"
BUTTON_MAIN_MENU = "🏠 Главное меню"

BUTTON_ADMIN_STATS = "📊 Статистика"
BUTTON_ADMIN_PENDING = "🕓 Ожидают проверки"
BUTTON_ADMIN_ACTIVE = "✅ Активные"
BUTTON_ADMIN_EXPIRED = "❌ Истёкшие"
BUTTON_ADMIN_REQUESTS = "📋 Все заявки"
BUTTON_ADMIN_PARTNERS = "🤝 Партнёры"
BUTTON_ADMIN_CODES = "🎟 Коды"


def get_main_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_PARTNERS, color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button(BUTTON_MY_CODES, color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(BUTTON_SUBSCRIPTION, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_HELP, color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()


def get_nav_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_BACK, color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(BUTTON_MAIN_MENU, color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()


def get_admin_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_ADMIN_STATS, color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()
