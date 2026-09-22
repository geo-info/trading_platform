"""inprotect — JS-проверка отпечатка браузера перед выдачей страницы.

Площадка на первый запрос отдаёт 429 и страницу со скриптом вместо содержимого.
Скрипт собирает отпечаток браузера — canvas, WebGL, метрики шрифтов, часовой
пояс, ``navigator.webdriver`` — кладёт его base64url в куки ``inprotect_ok_<N>``
и ``inprotect_fp_<N>`` и перезагружает страницу. ``curl_cffi`` JS не исполняет,
поэтому без помощи цикл не замыкается и содержимое не приходит никогда.

Хук ответа, а не код в ``parse()``: парсер о проверке знать не должен, иначе
она протечёт в каждый метод каждого парсера на защищённых площадках. Куки после
прохождения живут сутки, так что проверка случается один раз за обход.

Привязки к конкретному сайту здесь нет: номер слота и nonce читаются со
страницы, хост — из URL ответа. Достаточно добавить хук в настройки::

    settings = Settings(response_hooks=(solve_inprotect,))
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: Номер слота и nonce — единственное, что меняется от страницы к странице.
_NONCE = re.compile(r'var nonce="([0-9a-f]+)"')
_SLOT = re.compile(r"inprotect_ok_(\d+)")

#: User-Agent из отпечатка. Держится согласованным с ``impersonate="chrome"``,
#: который шлёт macOS-UA: расхождение между заявленной платформой и реальным
#: User-Agent — само по себе признак. Меняете impersonate — меняйте и профиль.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)


def _fingerprint(nonce: str) -> str:
    """Отпечаток в том виде, в каком его кодирует скрипт страницы.

    Набор полей и их значения подобраны не на глаз — сервер проверяет и то,
    и другое. Установлено перебором на живой площадке:

    * пропуск **любого** из 14 полей даёт 429;
    * пустая строка, ноль или ``"err"`` вместо правдоподобного значения — 429
      (проверялись ua, plat, res, timeZone, canvas, webgl, threads, fonts,
      pluginsCount, chrome);
    * ``isHeadless: true`` — 429, очевидный признак бота площадка ловит;
    * обратный порядок ключей при тех же значениях — 429.

    Поэтому порядок ключей повторяет порядок присваиваний в JS
    (``JSON.stringify`` его сохраняет), а значения держатся согласованными
    между собой: macOS-UA, платформа MacIntel, рендерер Apple.
    """
    fields = {
        "ua": _UA,
        "plat": "MacIntel",
        "lang": "en-US",
        "languages": ["en-US", "en"],
        "timeZone": "Europe/Moscow",
        "pluginsCount": 5,
        # navigator.webdriver в обычном Chrome — false, а не undefined:
        # undefined выкинул бы ключ из JSON целиком.
        "isHeadless": False,
        "res": "1920x1080",
        "threads": 8,
        "chrome": 1,
        "touch": 0,
        # В JS это 32-битный знаковый хэш canvas и сумма метрик шрифтов.
        # Значения фиксированные: сервер смотрит на правдоподобие, а не на
        # разнообразие, и одного набора ему хватает.
        "canvas": -1268547842,
        "webgl": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)|Google Inc. (Apple)",
        "fonts": 4321,
        "nonce": nonce,
    }
    payload = json.dumps(fields, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


async def solve_inprotect(response: Any, *, session: Any, retry: Any) -> Any:
    """Хук ответа: пройти проверку inprotect и повторить запрос.

    Всё, что не 429 и не несёт челлендж, проходит насквозь — на площадках
    без проверки хук ничего не делает и ничего не стоит.

    Повтор через ``retry()`` не тратит бюджет попыток ретрай-политики и не
    запускает хуки заново, так что зациклиться здесь нельзя: если проверка
    не прошла, наружу уходит второй 429 и дальше решает уже политика.
    """
    if response.status_code != 429:
        return response

    nonce = _NONCE.search(response.text)
    slot = _SLOT.search(response.text)
    if not (nonce and slot):
        # 429 без челленджа — это обычное «слишком часто», не наше дело.
        return response

    host = urlparse(str(response.url)).hostname
    number = slot.group(1)
    session.cookies.set(f"inprotect_ok_{number}", "1", domain=host, path="/")
    session.cookies.set(f"inprotect_fp_{number}", _fingerprint(nonce.group(1)), domain=host, path="/")

    logger.info("inprotect: проверка пройдена, повторяем запрос к %s", response.url)
    return await retry()
