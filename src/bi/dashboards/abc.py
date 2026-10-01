"""Дашборд 4. ABC-анализ: на чём держится ассортимент.

Классическая задача закупок: какие позиции дают основную выручку, а какие занимают полку и деньги.
Группа A — первые 80% выручки, B — до 95%, C — остальное. Здесь же видно, сколько позиций из группы
C не продавались вообще: это кандидаты на вывод из ассортимента.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "abc"
TITLE: Final = "ABC-анализ ассортимента"
FOLDER: Final = "04-abc-анализ"
QUESTION: Final = "Какие товары дают выручку, а какие занимают полку?"
AUDIENCE: Final = "категорийный менеджер"

ABC_QUERY: Final = """
WITH по_товару AS (
    SELECT товар_id,
           sum(выручка) AS выручка,
           sum(себестоимость) AS себестоимость,
           sum(штук) AS штук
    FROM товар_месяц GROUP BY 1
),
накопление AS (
    SELECT т.товар_id,
           тов.название,
           тов.категория,
           т.выручка,
           т.выручка - т.себестоимость AS прибыль,
           т.штук,
           sum(т.выручка) OVER (ORDER BY т.выручка DESC) / sum(т.выручка) OVER () AS накопленная_доля
    FROM по_товару т JOIN товары тов USING (товар_id)
)
SELECT *,
       CASE WHEN накопленная_доля <= 0.8 THEN 'A'
            WHEN накопленная_доля <= 0.95 THEN 'B'
            ELSE 'C' END AS группа
FROM накопление
ORDER BY выручка DESC
"""


def build(store: Store, out: Path) -> Path:
    items = store.query(ABC_QUERY)
    total_revenue = float(items["выручка"].sum())
    catalog = int(store.value("SELECT count(*) FROM товары"))
    never_sold = catalog - len(items)

    groups = (
        items.groupby("группа")
        .agg(товаров=("товар_id", "size"), выручка=("выручка", "sum"), прибыль=("прибыль", "sum"))
        .reset_index()
    )

    categories = store.query(
        """
        SELECT категория, sum(выручка) AS выручка, sum(выручка - себестоимость) AS прибыль,
               count(DISTINCT товар_id) AS товаров
        FROM товар_месяц GROUP BY 1 ORDER BY выручка DESC
        """
    )

    group_a = groups[groups["группа"] == "A"].iloc[0]
    cards = [
        Card("Товаров в группе A", number(float(group_a["товаров"])), f"из {number(catalog)} в каталоге"),
        Card("Доля выручки группы A", percent(float(group_a["выручка"]) / total_revenue), "первые 80% по определению"),
        Card(
            "Не продавались ни разу",
            number(never_sold),
            "кандидаты на вывод из ассортимента" if never_sold else "весь каталог хотя бы раз продавался",
            tone="внимание" if never_sold else "",
        ),
        Card("Выручка ассортимента", money(total_revenue), "за весь период"),
    ]

    blocks = [
        Block(
            title="Группы ABC",
            subtitle="A — первые 80% выручки, B — до 95%, C — остальное",
            body=table(
                ["Группа", "Товаров", "Доля позиций", "Выручка", "Доля выручки", "Прибыль"],
                [
                    [
                        str(row["группа"]),
                        number(float(row["товаров"])),
                        percent(float(row["товаров"]) / len(items)),
                        money(float(row["выручка"])),
                        percent(float(row["выручка"]) / total_revenue),
                        money(float(row["прибыль"])),
                    ]
                    for _, row in groups.iterrows()
                ],
                align="l" + "rrrrr",
            ),
        ),
        Block(
            title="Категории",
            subtitle="выручка и прибыль за весь период",
            body=bars(
                {str(row["категория"]): float(row["выручка"]) for _, row in categories.iterrows()},
                horizontal=True,
            ),
        ),
        Block(
            title="Топ-15 товаров",
            body=table(
                ["Товар", "Категория", "Группа", "Выручка", "Прибыль", "Штук"],
                [
                    [
                        str(row["название"]),
                        str(row["категория"]),
                        str(row["группа"]),
                        money(float(row["выручка"])),
                        money(float(row["прибыль"])),
                        number(float(row["штук"])),
                    ]
                    for _, row in items.head(15).iterrows()
                ],
                align="lll" + "rrr",
            ),
        ),
        Block(
            title="Хвост ассортимента",
            subtitle="группа C: продаются, но почти не дают выручки",
            body=table(
                ["Товар", "Категория", "Выручка", "Штук"],
                [
                    [
                        str(row["название"]),
                        str(row["категория"]),
                        money(float(row["выручка"])),
                        number(float(row["штук"])),
                    ]
                    for _, row in items[items["группа"] == "C"].tail(10).iterrows()
                ],
                align="ll" + "rr",
            ),
            note=(
                "Прежде чем выводить позицию из ассортимента, стоит посмотреть, не покупают ли её вместе "
                "с чем-то дорогим: в этих данных такой связи не видно, но в жизни она бывает решающей."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина товар_месяц и справочник товаров",
        prepared_on=datetime.now(UTC).date(),
        metrics_note="Группа определяется накопленной долей выручки, посчитанной оконной функцией.",
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
