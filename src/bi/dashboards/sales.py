"""Дашборд 1. Продажи сети: сколько заработали и за счёт чего.

Первый экран для коммерческого директора. Пять чисел сверху отвечают на вопрос «как дела», ниже —
откуда это взялось: динамика по месяцам, структура по категориям и вклад магазинов.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, change, lines, money, number, page, percent, stacked, table
from bi.warehouse import Store

NAME: Final = "sales"
TITLE: Final = "Продажи сети"
FOLDER: Final = "01-продажи"
QUESTION: Final = "Сколько сеть заработала за период и за счёт чего?"
AUDIENCE: Final = "коммерческий директор"


def build(store: Store, out: Path) -> Path:
    totals = store.query(
        """
        SELECT sum(выручка) AS выручка,
               sum(прибыль) AS прибыль,
               sum(чеков) AS чеков,
               sum(выручка) / nullif(sum(чеков), 0) AS средний_чек,
               sum(прибыль) / nullif(sum(выручка), 0) AS маржинальность,
               min(месяц) AS начало,
               max(месяц) AS конец
        FROM продажи_месяц
        """
    ).iloc[0]

    monthly = store.query(
        """
        SELECT месяц, sum(выручка) AS выручка, sum(прибыль) AS прибыль, sum(чеков) AS чеков
        FROM продажи_месяц GROUP BY 1 ORDER BY 1
        """
    )
    last, previous = float(monthly["выручка"].iloc[-1]), float(monthly["выручка"].iloc[-2])

    categories = store.query(
        """
        SELECT месяц, категория, sum(выручка) AS выручка
        FROM продажи_позиции GROUP BY 1, 2 ORDER BY 1
        """
    )
    months = [f"{value:%m.%y}" for value in monthly["месяц"]]
    by_category = {
        str(name): [
            float(categories[(categories["месяц"] == month) & (categories["категория"] == name)]["выручка"].sum())
            for month in monthly["месяц"]
        ]
        for name in sorted(categories["категория"].unique())
    }

    shops = store.query(
        """
        SELECT магазин, город, формат, sum(выручка) AS выручка, sum(прибыль) AS прибыль,
               sum(чеков) AS чеков, sum(выручка) / nullif(sum(чеков), 0) AS средний_чек
        FROM продажи_месяц GROUP BY 1, 2, 3 ORDER BY выручка DESC
        """
    )

    cards = [
        Card("Выручка", money(float(totals["выручка"])), f"с {totals['начало']:%m.%Y} по {totals['конец']:%m.%Y}"),
        Card(
            "Валовая прибыль",
            money(float(totals["прибыль"])),
            f"маржинальность {percent(float(totals['маржинальность']))}",
        ),
        Card("Чеков", number(float(totals["чеков"])), "число покупок, а не товаров"),
        Card("Средний чек", money(float(totals["средний_чек"]), 0), "выручка, делённая на чеки"),
        Card(
            "Последний месяц",
            money(last),
            f"к прошлому месяцу {change(last / previous - 1)}",
            tone="хорошо" if last >= previous else "внимание",
        ),
    ]

    blocks = [
        Block(
            title="Динамика по месяцам",
            subtitle="выручка и валовая прибыль, ₽",
            body=lines(
                months,
                {
                    "выручка": [float(value) for value in monthly["выручка"]],
                    "прибыль": [float(value) for value in monthly["прибыль"]],
                },
            ),
            note="Провал в феврале 2026 года — плановый ремонт одного магазина, а не падение спроса.",
        ),
        Block(
            title="Структура выручки по категориям",
            subtitle="накопительно, ₽ в месяц",
            body=stacked(months, by_category),
        ),
        Block(
            title="Магазины",
            subtitle="весь период",
            body=table(
                ["Магазин", "Город", "Формат", "Выручка", "Прибыль", "Чеков", "Средний чек"],
                [
                    [
                        str(row["магазин"]),
                        str(row["город"]),
                        str(row["формат"]),
                        money(float(row["выручка"])),
                        money(float(row["прибыль"])),
                        number(float(row["чеков"])),
                        money(float(row["средний_чек"]), 0),
                    ]
                    for _, row in shops.iterrows()
                ],
                align="lll" + "rrrr",
            ),
        ),
        Block(
            title="Вклад магазинов в выручку",
            subtitle="доля от общей выручки сети",
            body=bars(
                {str(row["магазин"]): float(row["выручка"]) for _, row in shops.iterrows()},
                horizontal=True,
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины продажи_месяц и продажи_позиции",
        prepared_on=datetime.now(UTC).date(),
        metrics_note="Выручка — со скидкой, но до вычета возвратов; определения всех метрик — в словаре метрик.",
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
