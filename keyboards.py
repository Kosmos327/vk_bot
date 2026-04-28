from vk_api.keyboard import VkKeyboard, VkKeyboardColor


BUTTON_BENEFITS = "Что входит"
BUTTON_PAYMENT = "Как оплатить"
BUTTON_PAID = "Я оплатил"
BUTTON_PARTNERS = "Партнёры"
BUTTON_GET_DISCOUNT = "Получить скидку"
BUTTON_QUESTION = "Задать вопрос"
BUTTON_MY_LINK = "Моя ссылка"
BUTTON_ADMIN_STATS = "📊 Статистика"
BUTTON_ADMIN_PENDING = "🕓 Ожидают проверки"
BUTTON_ADMIN_ACTIVE = "✅ Активные"
BUTTON_ADMIN_EXPIRED = "❌ Истёкшие"
BUTTON_ADMIN_REQUESTS = "📋 Все заявки"
BUTTON_ADMIN_PARTNERS = "🤝 Партнёры"
BUTTON_ADMIN_CODES = "🎟 Коды"


def get_main_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_BENEFITS, color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(BUTTON_PAYMENT, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_PAID, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_MY_LINK, color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button(BUTTON_GET_DISCOUNT, color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button(BUTTON_PARTNERS, color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(BUTTON_QUESTION, color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()


def get_admin_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_ADMIN_STATS, color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(BUTTON_ADMIN_PENDING, color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button(BUTTON_ADMIN_ACTIVE, color=VkKeyboardColor.POSITIVE)
    keyboard.add_button(BUTTON_ADMIN_EXPIRED, color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_ADMIN_REQUESTS, color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(BUTTON_ADMIN_PARTNERS, color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button(BUTTON_ADMIN_CODES, color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()
