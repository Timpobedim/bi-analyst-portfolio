"""Дашборд 2. План и факт: кто закрыл план, а кто нет — и насколько.

Экран для разбора на планёрке. Главное здесь — не подсветить отстающих, а отделить тех, кто не
выполнил план по своей части, от тех, у кого месяц был закрыт на ремонт: иначе разбор превращается
в поиск виноватых там, где виноват график работ.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, grouped_bars, money, page, percent, table
from bi.warehouse import Store

NAME: Final = "plan_fact"
TITLE: Final = "План и факт"
FOLDER: Final = "02-план-факт"
QUESTION: Final = "Выполняет ли сеть план и какие магазины отстают?"
AUDIENCE: Final = "директор по рознице"


def build(store: Store, out: Path) -> Path:
    monthly = store.query(
        """
        SELECT месяц, sum(выручка) AS факт, sum(план) AS план
        FROM продажи_месяц GROUP BY 1 ORDER BY 1
        """
    )
    totals = store.query(
        """
        SELECT sum(выручка) AS факт, sum(план) AS план,
               count(*) FILTER (WHERE выполнение_плана >= 1) AS выполнили,
               count(*) AS всего
        FROM продажи_месяц
        """
    ).iloc[0]

    shops = store.query(
        """
        SELECT магазин,
               город,
               sum(выручка) AS факт,
               sum(план) AS план,
               sum(выручка) / nullif(sum(план), 0) AS выполнение,
               count(*) FILTER (WHERE выполнение_плана >= 1) AS месяцев_с_планом,
               count(*) AS месяцев
        FROM продажи_месяц GROUP BY 1, 2 ORDER BY выполнение DESC
        """
    )

    worst = store.query(
        """
        SELECT магазин, месяц, выручка, план, выполнение_плана
        FROM продажи_месяц
        WHERE план IS NOT NULL
        ORDER BY выполнение_плана
        LIMIT 8
        """
    )

    overall = float(totals["факт"]) / float(totals["план"])
    cards = [
        Card(
            "Выполнение плана",
            percent(overall),
            f"факт {money(float(totals['факт']))} против плана {money(float(totals['план']))}",
            tone="хорошо" if overall >= 1 else "внимание",
        ),
        Card(
            "Месяцев с выполненным планом",
            f"{int(totals['выполнили'])} из {int(totals['всего'])}",
            "по всем магазинам вместе",
        ),
        Card("Отклонение", money(float(totals["факт"]) - float(totals["план"])), "факт минус план"),
        Card(
            "Магазинов выше плана",
            f"{int((shops['выполнение'] >= 1).sum())} из {len(shops)}",
            "за весь период",
        ),
    ]

    blocks = [
        Block(
            title="План и факт по месяцам",
            subtitle="₽",
            body=grouped_bars(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {
                    "факт": [float(value) for value in monthly["факт"]],
                    "план": [float(value) for value in monthly["план"]],
                },
            ),
        ),
        Block(
            title="Магазины",
            subtitle="за весь период",
            body=table(
                ["Магазин", "Город", "Факт", "План", "Выполнение", "Месяцев с планом"],
                [
                    [
                        str(row["магазин"]),
                        str(row["город"]),
                        money(float(row["факт"])),
                        money(float(row["план"])),
                        percent(float(row["выполнение"])),
                        f"{int(row['месяцев_с_планом'])} из {int(row['месяцев'])}",
                    ]
                    for _, row in shops.iterrows()
                ],
                align="ll" + "rrrr",
            ),
        ),
        Block(
            title="Худшие месяцы",
            subtitle="восемь случаев с наибольшим отставанием",
            body=table(
                ["Магазин", "Месяц", "Факт", "План", "Выполнение"],
                [
                    [
                        str(row["магазин"]),
                        f"{row['месяц']:%m.%Y}",
                        money(float(row["выручка"])),
                        money(float(row["план"])),
                        percent(float(row["выполнение_плана"])),
                    ]
                    for _, row in worst.iterrows()
                ],
                align="ll" + "rrr",
            ),
            note=(
                "Февраль 2026 года у одного магазина — месяц ремонта: план не снимали, работать было негде. "
                "Такие случаи нужно разбирать отдельно, а не считать провалом команды."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина продажи_месяц (факт и план из таблицы план)",
        prepared_on=datetime.now(UTC).date(),
        metrics_note="Выполнение плана = выручка / план выручки; в месяц ремонта магазин закрыт.",
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
