"""CookieJar для hh.ru доменов."""

import re
from http.cookiejar import Cookie, MozillaCookieJar


class HHOnlyCookieJar(MozillaCookieJar):
    """Хранилище, которое сохраняет куки только с hh.ru и связанных доменов."""

    def set_cookie(self, cookie: Cookie):
        # Регулярное выражение для проверки доменов hh.ru, hh.kz, hh.uz и т.д.
        pattern = r"(\.|^)hh\.(ru|kz|uz|ua|by|net|com)[.]?$"
        if re.search(pattern, cookie.domain):
            super().set_cookie(cookie)
