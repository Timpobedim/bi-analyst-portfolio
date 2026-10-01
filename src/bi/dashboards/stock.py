"""Дашборд 11. Остатки и оборачиваемость: сколько денег лежит на полке.

Главная ловушка этой страницы — считать оборачиваемость по всей себестоимости продаж. Складской
учёт в выгрузке ведётся не по всему ассортименту, а по выборке позиций, и если поделить продажи
всего каталога на остаток этой выборки, оборачиваемость выйдет в разы лучше настоящей. Поэтому
здесь и числитель, и знаменатель ограничены одними и теми же товарами.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, lines, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "stock"
TITLE: Final = "Остатки и оборачиваемость"
FOLDER: Final = "11-остатки"
QUESTION: Final = "Сколько денег лежит в запасе и как быстро он обновляется?"
AUDIENCE: Final = "директор по логистике"

TURNOVER: Final = """
WITH под_учётом AS (SELECT DISTINCT товар_id FROM остатки),
продано AS (
    SELECT т.месяц, sum(т.себестоимость) AS себестоимость
    FROM товар_месяц т JOIN под_учётом у USING (товар_id)
    GROUP BY 1
),
запас AS (
    SELECT месяц, sum(остаток_рублей) AS остаток, sum(остаток_штук) AS штук
    FROM остатки_месяц GROUP BY 1
)
SELECT з.месяц,
       з.остаток,
       з.штук,
       п.себестоимость,
       п.себестоимость / nullif(з.остаток, 0) AS оборачиваемость,
       з.остаток / nullif(п.себестоимость, 0) * 30 AS запас_дней
FROM запас з LEFT JOIN продано п USING (месяц)
ORDER BY з.месяц
"""


def build(store: Store, out: Path) -> Path:
    monthly = store.query(TURNOVER)
    shops = store.query(
        """
        WITH под_учётом AS (SELECT DISTINCT товар_id FROM остатки),
        продано AS (
            SELECT п.магазин_id, sum(п.себестоимость) AS себестоимость
            FROM продажи_позиции п JOIN под_учётом у USING (товар_id)
            GROUP BY 1
        )
        SELECT м.название AS магазин,
               м.формат,
               avg(о.остаток_рублей) AS средний_остаток,
               avg(о.остаток_штук) AS среднее_штук,
               max(пр.себестоимость) / nullif(sum(о.остаток_рублей), 0) AS оборачиваемость
        FROM остатки_месяц о
        JOIN магазины м USING (магазин_id)
        LEFT JOIN продано пр USING (магазин_id)
        GROUP BY 1, 2
        ORDER BY оборачиваемость DESC
        """
    )

    tracked = int(store.value("SELECT count(DISTINCT товар_id) FROM остатки"))
    catalog = int(store.value("SELECT count(*) FROM товары"))
    last = monthly.iloc[-1]
    average_turnover = float(monthly["оборачиваемость"].dropna().mean())

    cards = [
        Card("Запас на последний месяц", money(float(last["остаток"])), f"{number(float(last['штук']))} штук"),
        Card("Оборачиваемость", number(average_turnover, 2) + " раза в месяц", "в среднем за период"),
        Card("Запас в днях", number(30 / average_turnover, 0), "на столько хватит при текущих продажах"),
        Card(
            "Ассортимент под складским учётом",
            f"{number(tracked)} из {number(catalog)}",
            percent(tracked / catalog) + " позиций",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Запас по месяцам",
            subtitle="остаток в рублях по себестоимости",
            body=lines(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {"остаток, ₽": [float(value) for value in monthly["остаток"]]},
            ),
        ),
        Block(
            title="Оборачиваемость по месяцам",
            subtitle="сколько раз за месяц обновился запас",
            body=lines(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {"раз в месяц": [float(value) for value in monthly["оборачиваемость"].fillna(0.0)]},
            ),
            note=(
                "Числитель — себестоимость проданного только по тем товарам, которые есть в складской "
                "выгрузке. Если взять продажи всего каталога, оборачиваемость завысится примерно втрое: "
                "продажи будут по девятистам позициям, а запас — по двумстам."
            ),
        ),
        Block(
            title="Месяцы",
            body=table(
                ["Месяц", "Остаток", "Штук", "Себестоимость продаж", "Оборачиваемость", "Запас, дней"],
                [
                    [
                        f"{row['месяц']:%m.%Y}",
                        money(float(row["остаток"])),
                        number(float(row["штук"])),
                        "—" if pd.isna(row["себестоимость"]) else money(float(row["себестоимость"])),
                        "—" if pd.isna(row["оборачиваемость"]) else number(float(row["оборачиваемость"]), 2),
                        "—" if pd.isna(row["запас_дней"]) else number(float(row["запас_дней"]), 0),
                    ]
                    for _, row in monthly.iterrows()
                ],
                align="l" + "rrrrr",
            ),
        ),
        Block(
            title="Средний запас по магазинам",
            subtitle="₽ по себестоимости",
            body=bars(
                {str(row["магазин"]): float(row["средний_остаток"]) for _, row in shops.iterrows()},
                horizontal=True,
            ),
            note=(
                "Остатки в выгрузке — снимок на первое число месяца, а не среднедневной запас. "
                "Колебания внутри месяца этим данным недоступны, и оборачиваемость по ним получается грубее."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины остатки_месяц и товар_месяц (пересечение по товарам под учётом)",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Оборачиваемость = себестоимость проданного за месяц / остаток на начало месяца, и то и другое "
            "— только по позициям складского учёта."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
