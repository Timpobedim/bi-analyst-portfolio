"""Дашборд 14. Качество данных: чему на остальных тринадцати страницах можно верить.

Такой страницы обычно нет, и зря: без неё любая цифра на дашборде выглядит одинаково надёжной.
Здесь собраны три разные вещи — автоматические проверки витрин, свежесть данных и список known
issues, то есть известных ограничений, которые проверками не ловятся и жить с которыми приходится.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from bi.dashboards import Dashboard
from bi.render import Block, Card, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "data_quality"
TITLE: Final = "Качество данных"
FOLDER: Final = "14-качество-данных"
QUESTION: Final = "Чему на этих дашбордах можно верить, а чему нельзя?"
AUDIENCE: Final = "все, кто пользуется дашбордами"


def build(store: Store, out: Path) -> Path:
    checks = store.check()
    passed = sum(1 for check in checks if check.ok)

    last_month = store.value("SELECT max(месяц) FROM продажи_месяц")
    last_day = pd.Timestamp(store.value("SELECT max(дата) FROM продажи_позиции")).date()
    today = datetime.now(UTC).date()
    age = (today - last_day).days

    revenue = float(store.value("SELECT sum(выручка) FROM продажи_месяц"))
    no_supplier = int(store.value("SELECT count(*) FROM товары WHERE поставщик IS NULL"))
    no_supplier_revenue = float(
        store.value("SELECT coalesce(sum(выручка), 0) FROM продажи_позиции WHERE поставщик IS NULL")
    )
    catalog = int(store.value("SELECT count(*) FROM товары"))
    tracked = int(store.value("SELECT count(DISTINCT товар_id) FROM остатки"))
    ad_orders = float(store.value("SELECT sum(заказов) FROM маркетинг_месяц"))
    online_receipts = float(
        store.value(
            "SELECT count(DISTINCT чек_id) FROM продажи_позиции WHERE канал IN ('самовывоз', 'доставка')"
        )
    )

    sizes = store.query(
        """
        SELECT table_name AS витрина, estimated_size AS строк
        FROM duckdb_tables() WHERE schema_name = 'main' ORDER BY estimated_size DESC
        """
    )

    known = [
        [
            "Выручка канала не измерена",
            "маркетинг",
            "Выручка сети разнесена по каналам пропорционально заказам. Окупаемость канала — оценка.",
        ],
        [
            "Реклама и касса не сходятся",
            "воронка",
            f"Реклама насчитала {number(ad_orders)} заказов, касса — {number(online_receipts)} чеков "
            f"самовывоза и доставки. Разница {percent(online_receipts / ad_orders - 1)}.",
        ],
        [
            "Складской учёт неполный",
            "остатки",
            f"Остатки ведутся по {number(tracked)} позициям из {number(catalog)}. Оборачиваемость считается "
            "только по ним, на весь ассортимент её распространять нельзя.",
        ],
        [
            "Пропуски в справочнике товаров",
            "маржинальность",
            f"У {number(no_supplier)} товаров не заполнен поставщик; на них приходится "
            f"{percent(no_supplier_revenue / revenue)} выручки. В отчётах они идут строкой «не указан».",
        ],
        [
            "Остатки — снимок, а не среднее",
            "остатки",
            "Запас зафиксирован на первое число месяца. Колебания внутри месяца данным недоступны.",
        ],
        [
            "Нет аренды и налогов",
            "финансы",
            "Операционный результат считается до аренды и налогов: этих расходов в источниках нет.",
        ],
        [
            "Возвраты не вычтены из выручки",
            "продажи, финансы",
            "Выручка на дашбордах — со скидкой, но до возвратов. Возвраты стоят отдельной строкой в финансах.",
        ],
    ]

    cards = [
        Card(
            "Проверок пройдено",
            f"{passed} из {len(checks)}",
            "прогоняются при каждой пересборке витрин",
            tone="хорошо" if passed == len(checks) else "плохо",
        ),
        Card("Данные по", f"{last_month:%m.%Y}", f"последний день — {last_day:%d.%m.%Y}"),
        Card(
            "Возраст данных",
            f"{age} дн.",
            "с последнего дня продаж до сборки страницы",
            tone="внимание" if age > 45 else "",
        ),
        Card("Известных ограничений", number(len(known)), "перечислены ниже полностью"),
    ]

    blocks = [
        Block(
            title="Известные ограничения",
            subtitle="то, что проверками не ловится, но влияет на выводы",
            body=table(
                ["Ограничение", "Где сказывается", "В чём дело"],
                known,
                align="lll",
            ),
            note=(
                "Этот список важнее зелёных галочек ниже. Проверки ловят поломки, а здесь перечислено то, "
                "что работает как задумано, но означает не то, что кажется на первый взгляд."
            ),
        ),
        Block(
            title="Проверки витрин",
            subtitle="выполняются при каждой сборке; страница собирается из того же кода, что и они",
            body=table(
                ["Витрина", "Проверка", "Итог"],
                [
                    [check.model, check.title.split(": ", 1)[-1], ("+ " if check.ok else "! ") + check.detail]
                    for check in checks
                ],
                align="lll",
            ),
        ),
        Block(
            title="Размеры таблиц",
            subtitle="строк в каждой таблице склада",
            body=table(
                ["Таблица", "Строк"],
                [[str(row["витрина"]), number(float(row["строк"]))] for _, row in sizes.iterrows()],
                align="lr",
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="проверки слоя моделей и сами витрины",
        prepared_on=today,
        metrics_note=(
            "Страница не написана руками: проверки и их результаты берутся из того же кода, который "
            "собирает витрины, поэтому она не может разойтись с тем, что происходит на самом деле."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
