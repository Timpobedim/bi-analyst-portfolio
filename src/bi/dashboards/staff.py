"""Дашборд 12. Персонал и сервис: выработка, текучесть и обращения покупателей.

Две темы на одной странице сведены намеренно. Выручка на сотрудника без текучести читается как
«где работают лучше», хотя высокая выработка часто означает просто нехватку людей — и тогда рядом
стоит рост увольнений и обращений о работе персонала. Разнесённые по разным экранам, эти числа
такой связи не показывают.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, lines, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "staff"
TITLE: Final = "Персонал и сервис"
FOLDER: Final = "12-персонал"
QUESTION: Final = "Сколько выручки приносит сотрудник и где люди не задерживаются?"
AUDIENCE: Final = "директор по персоналу"

BY_SHOP: Final = """
WITH год AS (SELECT max(месяц) - INTERVAL 12 MONTH AS граница FROM персонал_месяц)
SELECT м.название AS магазин,
       м.формат,
       avg(п.сотрудников) AS сотрудников,
       sum(п.уволено) AS уволено,
       sum(п.уволено) / nullif(avg(п.сотрудников), 0) AS текучесть,
       sum(пр.выручка) / nullif(avg(п.сотрудников), 0) AS выручка_на_сотрудника,
       sum(п.фот) / nullif(sum(пр.выручка), 0) AS фот_к_выручке
FROM персонал_месяц п
JOIN магазины м USING (магазин_id)
LEFT JOIN продажи_месяц пр USING (магазин_id, месяц)
WHERE п.месяц > (SELECT граница FROM год)
GROUP BY 1, 2
ORDER BY выручка_на_сотрудника DESC
"""


def build(store: Store, out: Path) -> Path:
    shops = store.query(BY_SHOP)
    monthly = store.query(
        """
        SELECT п.месяц,
               sum(п.сотрудников) AS сотрудников,
               sum(п.уволено) AS уволено,
               sum(п.фот) AS фот,
               sum(пр.выручка) / nullif(sum(п.сотрудников), 0) AS выручка_на_сотрудника,
               sum(п.фот) / nullif(sum(пр.выручка), 0) AS фот_к_выручке
        FROM персонал_месяц п
        LEFT JOIN продажи_месяц пр USING (магазин_id, месяц)
        GROUP BY 1 ORDER BY 1
        """
    )
    topics = store.query(
        """
        SELECT тема,
               sum(обращений) AS обращений,
               avg(среднее_время_часов) AS среднее_время,
               avg(девяностый_процентиль) AS хвост
        FROM обращения_месяц GROUP BY 1 ORDER BY обращений DESC
        """
    )
    complaints = store.query(
        """
        SELECT м.название AS магазин,
               sum(о.обращений) AS обращений,
               sum(о.обращений) * 1000.0 / nullif(sum(пр.чеков), 0) AS на_тысячу_чеков
        FROM обращения_месяц о
        JOIN магазины м USING (магазин_id)
        LEFT JOIN (SELECT магазин_id, sum(чеков) AS чеков FROM продажи_месяц GROUP BY 1) пр USING (магазин_id)
        GROUP BY 1 ORDER BY на_тысячу_чеков DESC
        """
    )

    last = monthly.iloc[-1]
    turnover = float(shops["уволено"].sum() / shops["сотрудников"].mean() / len(shops))
    worst = shops.sort_values("текучесть", ascending=False).iloc[0]

    cards = [
        Card("Сотрудников", number(float(last["сотрудников"])), f"на {last['месяц']:%m.%Y}"),
        Card("Фонд оплаты труда", money(float(last["фот"])), f"{percent(float(last['фот_к_выручке']))} выручки месяца"),
        Card("Выручка на сотрудника", money(float(last["выручка_на_сотрудника"]), 0), "за последний месяц"),
        Card(
            "Текучесть за год",
            percent(turnover),
            f"хуже всего в {worst['магазин']} — {percent(float(worst['текучесть']))}",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Выручка на сотрудника",
            subtitle="за последние 12 месяцев, ₽",
            body=bars(
                {str(row["магазин"]): float(row["выручка_на_сотрудника"]) for _, row in shops.iterrows()},
                horizontal=True,
            ),
            note=(
                "Высокая выработка — не всегда хорошая новость: тот же результат даёт нехватка людей. "
                "Смотреть её нужно вместе со следующей таблицей, где стоит текучесть."
            ),
        ),
        Block(
            title="Магазины",
            subtitle="за последние 12 месяцев",
            body=table(
                ["Магазин", "Формат", "Сотрудников", "Уволено", "Текучесть", "Выручка на сотрудника", "ФОТ к выручке"],
                [
                    [
                        str(row["магазин"]),
                        str(row["формат"]),
                        number(float(row["сотрудников"]), 1),
                        number(float(row["уволено"])),
                        percent(float(row["текучесть"])),
                        money(float(row["выручка_на_сотрудника"]), 0),
                        percent(float(row["фот_к_выручке"])),
                    ]
                    for _, row in shops.iterrows()
                ],
                align="ll" + "rrrrr",
            ),
        ),
        Block(
            title="ФОТ к выручке по месяцам",
            subtitle="доля",
            body=lines(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {"ФОТ к выручке": [float(value) for value in monthly["фот_к_выручке"].fillna(0.0)]},
            ),
        ),
        Block(
            title="Обращения покупателей",
            subtitle="за весь период",
            body=table(
                ["Тема", "Обращений", "Среднее время решения", "Граница худших 10%"],
                [
                    [
                        str(row["тема"]),
                        number(float(row["обращений"])),
                        number(float(row["среднее_время"]), 1) + " ч",
                        number(float(row["хвост"]), 1) + " ч",
                    ]
                    for _, row in topics.iterrows()
                ],
                align="l" + "rrr",
            ),
            note=(
                "Среднее время решения скрывает хвост: в последнем столбце — граница (в среднем по "
                "месяцам), за которой лежат самые долгие десять процентов обращений. Именно они "
                "попадают в отзывы, а среднее выглядит благополучно."
            ),
        ),
        Block(
            title="Обращения на тысячу чеков",
            subtitle="так магазины разного размера сравнимы",
            body=bars(
                {str(row["магазин"]): float(row["на_тысячу_чеков"]) for _, row in complaints.iterrows()},
                horizontal=True,
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины персонал_месяц, обращения_месяц и продажи_месяц",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Текучесть = уволенные за год к средней численности. ФОТ — сумма окладов работающих "
            "в этом месяце, без премий и налогов: их в исходных данных нет."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
