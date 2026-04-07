"""
Ключевые слова для поиска ссылок на страницы контактов.

Используются при парсинге главной страницы сайта работодателя
для обнаружения ссылок на страницы с контактной информацией.
"""

CONTACT_KEYWORDS = [
    "контакты",
    "contact",
    "contact us",
    "contacts",
    "связаться с нами",
    "связаться",
    "обратная связь",
    "feedback",
    "write us",
    "send message",
    "телефон",
    "phone",
    "телефоны",
    "email",
    "e-mail",
    "почта",
    "адрес",
    "address",
    "офис",
    "office",
    "location",
    "как нас найти",
    "поддержка",
    "support",
    "contact form",
    "форма обратной связи",
    "написать нам",
    "reach us",
    "contact info",
    "contact information",
]

__all__ = ("CONTACT_KEYWORDS",)
