"""Дашборд 5. Маржинальность и скидки: где зарабатывают, а где отдают.

Выручка и прибыль ведут себя по-разному: категория может расти в обороте и при этом терять деньги,
если рост держится на скидке. Поэтому здесь рядом стоят три числа — выручка, валовая прибыль и то,
сколько отдано скидкой; последнее в отчётах обычно не показывают вовсе, потому что в кассовых
данных его нет напрямую, оно считается от цены без скидки.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, lines, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "margin"
TITLE: Final = "Маржинальность и скидки"
FOLDER: Final = "05-маржинальность"
QUESTION: Final = "Где сеть зарабатывает и сколько отдаёт скидкой?"
AUDIENCE: Final = "категорийный менеджер"

BY_CATEGORY: Final = """
SELECT категория,
       sum(выручка) AS выручка,
       sum(выручка) - sum(себестоимость) AS прибыль,
       (sum(выручка) - sum(себестоимость)) / nullif(sum(выручка), 0) AS маржинальность,
       sum(количество * цена / nullif(1 - скидка, 0)) - sum(выручка) AS отдано_скидкой,
       count(*) FILTER (WHERE скидка > 0) * 1.0 / count(*) AS доля_со_скидкой
FROM продажи_позиции
GROUP BY 1
ORDER BY прибыль DESC
"""

BY_SUPPLIER: Final = """
SELECT coalesce(поставщик, 'не указан') AS поставщик,
       count(DISTINCT товар_id) AS товаров,
       sum(выручка) AS выручка,
       sum(выручка) - sum(себестоимость) AS прибыль,
       (sum(выручка) - sum(себестоимость)) / nullif(sum(выручка), 0) AS маржинальность
FROM продажи_позиции
GROUP BY 1
ORDER BY выручка DESC
"""


def build(store: Store, out: Path) -> Path:
    categories = store.query(BY_CATEGORY)
    suppliers = store.query(BY_SUPPLIER)
    monthly = store.query(
        """
        SELECT месяц,
               (sum(выручка) - sum(себестоимость)) / nullif(sum(выручка), 0) AS маржинальность,
               (sum(количество * цена / nullif(1 - скидка, 0)) - sum(выручка))
                   / nullif(sum(количество * цена / nullif(1 - скидка, 0)), 0) AS доля_скидки
        FROM продажи_позиции GROUP BY 1 ORDER BY 1
        """
    )

    revenue = float(categories["выручка"].sum())
    profit = float(categories["прибыль"].sum())
    discount = float(categories["отдано_скидкой"].sum())
    best = categories.sort_values("маржинальность", ascending=False).iloc[0]
    worst = categories.sort_values("маржинальность").iloc[0]
    unknown = suppliers[suppliers["поставщик"] == "не указан"]

    cards = [
        Card("Валовая прибыль", money(profit), f"маржинальность {percent(profit / revenue)}"),
        Card("Отдано скидкой", money(discount), f"{percent(discount / (revenue + discount))} от цены без скидки"),
        Card(
            "Лучшая категория",
            str(best["категория"]),
            percent(float(best["маржинальность"])) + " маржи",
            tone="хорошо",
        ),
        Card(
            "Худшая категория",
            str(worst["категория"]),
            percent(float(worst["маржинальность"])) + " маржи",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Категории",
            subtitle="выручка, прибыль и цена скидок",
            body=table(
                ["Категория", "Выручка", "Прибыль", "Маржинальность", "Отдано скидкой", "Позиций со скидкой"],
                [
                    [
                        str(row["категория"]),
                        money(float(row["выручка"])),
                        money(float(row["прибыль"])),
                        percent(float(row["маржинальность"])),
                        money(float(row["отдано_скидкой"])),
                        percent(float(row["доля_со_скидкой"])),
                    ]
                    for _, row in categories.iterrows()
                ],
                align="l" + "rrrrr",
            ),
            note=(
                "«Отдано скидкой» — разница между ценой без скидки и тем, что пробито на кассе. "
                "Это не убыток: часть этих покупок без скидки просто не состоялась бы. Но это цена, "
                "которую стоит знать, прежде чем расширять акцию."
            ),
        ),
        Block(
            title="Прибыль по категориям",
            subtitle="валовая прибыль за весь период, ₽",
            body=bars(
                {str(row["категория"]): float(row["прибыль"]) for _, row in categories.iterrows()},
                horizontal=True,
            ),
        ),
        Block(
            title="Маржинальность и скидки по месяцам",
            subtitle="доли; линии идут в противофазе, когда рост держится на акциях",
            body=lines(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {
                    "маржинальность": [float(value) for value in monthly["маржинальность"]],
                    "доля скидки": [float(value) for value in monthly["доля_скидки"]],
                },
            ),
        ),
        Block(
            title="Поставщики",
            body=table(
                ["Поставщик", "Товаров", "Выручка", "Прибыль", "Маржинальность"],
                [
                    [
                        str(row["поставщик"]),
                        number(float(row["товаров"])),
                        money(float(row["выручка"])),
                        money(float(row["прибыль"])),
                        percent(float(row["маржинальность"])),
                    ]
                    for _, row in suppliers.iterrows()
                ],
                align="l" + "rrrr",
            ),
            note=(
                "Строка «не указан» — не поставщик, а дыра в справочнике: "
                + (
                    f"{number(float(unknown['товаров'].iloc[0]))} товаров без заполненного поля, "
                    f"и на них приходится {percent(float(unknown['выручка'].iloc[0]) / revenue)} выручки. "
                    if len(unknown)
                    else ""
                )
                + "Прятать такую строку нельзя: тогда сумма по поставщикам не сойдётся с общей выручкой."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина продажи_позиции",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Маржинальность здесь валовая: выручка минус себестоимость товара. Аренда, зарплата и "
            "реклама в неё не входят — они на дашборде финансов."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
