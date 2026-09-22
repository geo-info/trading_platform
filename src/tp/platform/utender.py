"""uTender — банкротные торги, движок iTender.

В манифесте эталонного парсера площадка помечена сломанной: «пагинация
не двигается — перекачивает page 1». На обычных postback-ах, без ajax-дельты,
она идёт нормально — проверено переходом со страницы 1 на 2.

uv run python -m tp.platform.utender
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Utender(TenderFogsoft):
    name = "utender"
    DOMAIN = "http://utender.ru"


if __name__ == "__main__":
    main(Utender)
