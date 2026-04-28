from vk_api.keyboard import VkKeyboard, VkKeyboardColor


BUTTON_BENEFITS = "Что входит"
BUTTON_PAYMENT = "Как оплатить"
BUTTON_PAID = "Я оплатил"
BUTTON_PARTNERS = "Партнёры"
BUTTON_QUESTION = "Задать вопрос"


def get_main_keyboard() -> str:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(BUTTON_BENEFITS, color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(BUTTON_PAYMENT, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_PAID, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(BUTTON_PARTNERS, color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(BUTTON_QUESTION, color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()
