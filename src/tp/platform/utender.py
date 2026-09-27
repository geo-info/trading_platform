"""uTender — банкротные торги, движок iTender.

В манифесте эталонного парсера площадка помечена сломанной: «пагинация
не двигается — перекачивает page 1». На обычных postback-ах, без ajax-дельты,
она идёт нормально — проверено переходом со страницы 1 на 2.

uv run python -m run_all utender
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Utender(TenderFogsoft):
    name = "utender"
    DOMAIN = "http://utender.ru"
