"""Дашборд 3. Магазины: сопоставимые продажи и выработка с метра.

Сравнивать магазины «в лоб» по выручке бессмысленно: гипермаркет всегда обгонит точку у дома.
Поэтому здесь два сравнимых показателя — сопоставимые продажи (последние двенадцать месяцев к
предыдущим двенадцати по тем магазинам, которые работали в обоих периодах) и выручка с метра.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, change, grouped_bars, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "stores"
TITLE: Final = "Магазины: сопоставимые продажи"
FOLDER: Final = "03-магазины"
QUESTION: Final = "Какие магазины растут на самом деле, а не за счёт размера?"
AUDIENCE: Final = "директор по рознице"

LFL_QUERY: Final = """
WITH границы AS (
    SELECT max(месяц) AS последний FROM продажи_месяц
),
периоды AS (
    SELECT п.магазин_id,
           п.магазин,
           п.город,
           п.формат,
           sum(п.выручка) FILTER (
               WHERE п.месяц > (SELECT последний FROM границы) - INTERVAL 12 MONTH
           ) AS текущий,
           sum(п.выручка) FILTER (
               WHERE п.месяц <= (SELECT последний FROM границы) - INTERVAL 12 MONTH
                 AND п.месяц > (SELECT последний FROM границы) - INTERVAL 24 MONTH
           ) AS прошлый,
           count(*) FILTER (
               WHERE п.месяц > (SELECT последний FROM границы) - INTERVAL 12 MONTH AND п.выручка > 0
           ) AS месяцев_в_работе
    FROM продажи_месяц п
    GROUP BY 1, 2, 3, 4
)
SELECT п.*, м.площадь, м.открыт,
       текущий / nullif(прошлый, 0) - 1 AS lfl,
       текущий / nullif(м.площадь, 0) AS выручка_с_метра
FROM периоды п
JOIN магазины м USING (магазин_id)
ORDER BY lfl DESC NULLS LAST
"""


def build(store: Store, out: Path) -> Path:
    shops = store.query(LFL_QUERY)
    comparable = shops.dropna(subset=["lfl"])
    network_lfl = float(comparable["текущий"].sum() / comparable["прошлый"].sum() - 1) if len(comparable) else 0.0
    full_year = shops[shops["месяцев_в_работе"] >= 12]

    formats = store.query(
        """
        SELECT формат,
               count(DISTINCT магазин_id) AS магазинов,
               sum(выручка) AS выручка,
               sum(выручка) / nullif(sum(чеков), 0) AS средний_чек,
               sum(прибыль) / nullif(sum(выручка), 0) AS маржинальность
        FROM продажи_месяц GROUP BY 1 ORDER BY выручка DESC
        """
    )

    cards = [
        Card(
            "Сопоставимые продажи",
            change(network_lfl),
            f"по {len(comparable)} магазинам, работавшим оба года",
            tone="хорошо" if network_lfl >= 0 else "плохо",
        ),
        Card("Магазинов в сети", number(len(shops)), f"сравнимых год к году — {len(comparable)}"),
        Card(
            "Лучший по росту",
            str(comparable.iloc[0]["магазин"]) if len(comparable) else "—",
            change(float(comparable.iloc[0]["lfl"])) if len(comparable) else "",
            tone="хорошо",
        ),
        Card(
            "Худший по росту",
            str(comparable.iloc[-1]["магазин"]) if len(comparable) else "—",
            change(float(comparable.iloc[-1]["lfl"])) if len(comparable) else "",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Год к году по магазинам",
            subtitle="выручка за последние 12 месяцев и за предыдущие 12, ₽",
            body=grouped_bars(
                [str(row["магазин"]) for _, row in comparable.iterrows()],
                {
                    "последние 12 месяцев": [float(row["текущий"]) for _, row in comparable.iterrows()],
                    "предыдущие 12": [float(row["прошлый"]) for _, row in comparable.iterrows()],
                },
            ),
            note=(
                "Рост показан двумя столбиками, а не одной цифрой роста: столбик падения и столбик роста "
                "на общей шкале видно сразу, а «−4%» и «+4%» в одинаковых по длине полосках — нет."
            ),
        ),
        Block(
            title="Выручка с квадратного метра",
            subtitle="за последние 12 месяцев, ₽ на м²",
            body=bars(
                {
                    str(row["магазин"]): float(row["выручка_с_метра"])
                    for _, row in full_year.sort_values("выручка_с_метра", ascending=False).iterrows()
                },
                horizontal=True,
            ),
            note=(
                "Точка у дома проигрывает гипермаркету по обороту, но обычно выигрывает по отдаче с метра. "
                "Магазины, отработавшие неполный год, сюда не попали: у них выручка за 12 месяцев неполная, "
                "и делить её на площадь наравне с остальными нельзя."
            ),
        ),
        Block(
            title="Форматы",
            body=table(
                ["Формат", "Магазинов", "Выручка", "Средний чек", "Маржинальность"],
                [
                    [
                        str(row["формат"]),
                        number(float(row["магазинов"])),
                        money(float(row["выручка"])),
                        money(float(row["средний_чек"]), 0),
                        percent(float(row["маржинальность"])),
                    ]
                    for _, row in formats.iterrows()
                ],
                align="l" + "rrrr",
            ),
        ),
        Block(
            title="Все магазины",
            body=table(
                ["Магазин", "Город", "Формат", "Открыт", "Площадь", "Выручка за год", "Сопоставимые продажи"],
                [
                    [
                        str(row["магазин"]),
                        str(row["город"]),
                        str(row["формат"]),
                        f"{row['открыт']:%m.%Y}",
                        number(float(row["площадь"])),
                        money(float(row["текущий"])),
                        change(float(row["lfl"])) if row["lfl"] == row["lfl"] else "нет базы сравнения",
                    ]
                    for _, row in shops.iterrows()
                ],
                align="llll" + "rrr",
            ),
            note=(
                "«Нет базы сравнения» — магазин открылся внутри периода, и прошлого года у него просто не "
                "было. Это не ноль и не провал: подставить сюда ноль значило бы показать падение на 100%."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина продажи_месяц и справочник магазинов",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Сопоставимые продажи (LFL) считаются только по магазинам, работавшим в обоих периодах. "
            "Месяц ремонта из расчёта не исключается — он и должен портить показатель тому, кто не работал."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
