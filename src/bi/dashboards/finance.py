"""Дашборд 13. Финансовый результат: от выручки до операционной прибыли.

Собирает в один отчёт то, что разложено по остальным страницам: выручку и себестоимость из продаж,
фонд оплаты труда из персонала, рекламу из маркетинга и возвраты. Аренды и налогов в исходных
данных нет, поэтому строка называется операционным результатом до аренды и налогов, а не прибылью:
приписывать отчёту точность, которой в данных нет, — самый быстрый способ его обесценить.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, change, lines, money, page, percent, stacked, table
from bi.warehouse import Store

NAME: Final = "finance"
TITLE: Final = "Финансовый результат"
FOLDER: Final = "13-финансы"
QUESTION: Final = "Что остаётся у сети после себестоимости, зарплат и рекламы?"
AUDIENCE: Final = "финансовый директор"

MONTHLY: Final = """
WITH продажи AS (
    SELECT месяц, sum(выручка) AS выручка, sum(выручка) - sum(прибыль) AS себестоимость, sum(прибыль) AS валовая
    FROM продажи_месяц GROUP BY 1
),
зарплата AS (SELECT месяц, sum(фот) AS фот FROM персонал_месяц GROUP BY 1),
реклама AS (SELECT CAST(месяц AS TIMESTAMP) AS месяц, sum(расходы) AS реклама FROM маркетинг_месяц GROUP BY 1),
возврат AS (SELECT месяц, sum(сумма_возвратов) AS возвраты FROM возвраты_месяц GROUP BY 1)
SELECT п.месяц,
       п.выручка,
       п.себестоимость,
       п.валовая,
       coalesce(з.фот, 0) AS фот,
       coalesce(р.реклама, 0) AS реклама,
       coalesce(в.возвраты, 0) AS возвраты,
       п.валовая - coalesce(з.фот, 0) - coalesce(р.реклама, 0) - coalesce(в.возвраты, 0) AS результат
FROM продажи п
LEFT JOIN зарплата з USING (месяц)
LEFT JOIN реклама р USING (месяц)
LEFT JOIN возврат в USING (месяц)
ORDER BY п.месяц
"""


def build(store: Store, out: Path) -> Path:
    monthly = store.query(MONTHLY)
    shops = store.query(
        """
        WITH доля AS (
            SELECT магазин_id, sum(выручка) AS выручка, sum(прибыль) AS валовая,
                   sum(выручка) / (SELECT sum(выручка) FROM продажи_месяц) AS вес
            FROM продажи_месяц GROUP BY 1
        ),
        зарплата AS (SELECT магазин_id, sum(фот) AS фот FROM персонал_месяц GROUP BY 1),
        возврат AS (SELECT магазин_id, sum(сумма_возвратов) AS возвраты FROM возвраты_месяц GROUP BY 1)
        SELECT м.название AS магазин,
               м.формат,
               д.выручка,
               д.валовая,
               coalesce(з.фот, 0) AS фот,
               д.вес * (SELECT sum(расходы) FROM маркетинг_месяц) AS реклама,
               coalesce(в.возвраты, 0) AS возвраты,
               д.валовая - coalesce(з.фот, 0) - д.вес * (SELECT sum(расходы) FROM маркетинг_месяц)
                   - coalesce(в.возвраты, 0) AS результат
        FROM доля д
        JOIN магазины м USING (магазин_id)
        LEFT JOIN зарплата з USING (магазин_id)
        LEFT JOIN возврат в USING (магазин_id)
        ORDER BY результат DESC
        """
    )

    revenue = float(monthly["выручка"].sum())
    gross = float(monthly["валовая"].sum())
    result = float(monthly["результат"].sum())
    last, previous = float(monthly["результат"].iloc[-1]), float(monthly["результат"].iloc[-2])
    losing = shops[shops["результат"] < 0]

    months = [f"{value:%m.%y}" for value in monthly["месяц"]]
    rows = [
        ("Выручка", "выручка"),
        ("Себестоимость товара", "себестоимость"),
        ("Валовая прибыль", "валовая"),
        ("Фонд оплаты труда", "фот"),
        ("Реклама", "реклама"),
        ("Возвраты", "возвраты"),
        ("Операционный результат", "результат"),
    ]

    cards = [
        Card("Выручка", money(revenue), "за 24 месяца"),
        Card("Валовая прибыль", money(gross), percent(gross / revenue) + " выручки"),
        Card(
            "Операционный результат",
            money(result),
            percent(result / revenue) + " выручки, до аренды и налогов",
            tone="хорошо" if result > 0 else "плохо",
        ),
        Card(
            "Последний месяц",
            money(last),
            f"к прошлому {change(last / previous - 1)}" if previous else "",
            tone="хорошо" if last >= previous else "внимание",
        ),
    ]

    blocks = [
        Block(
            title="Отчёт по месяцам",
            subtitle="₽",
            body=table(
                ["Статья", *[f"{value:%m.%y}" for value in monthly["месяц"].iloc[-6:]], "Всего"],
                [
                    [
                        label,
                        *[money(float(value)) for value in monthly[column].iloc[-6:]],
                        money(float(monthly[column].sum())),
                    ]
                    for label, column in rows
                ],
                align="l" + "r" * 7,
            ),
            note="В таблице показаны последние шесть месяцев и итог за весь период — иначе она не влезает на экран.",
        ),
        Block(
            title="Структура расходов",
            subtitle="себестоимость, зарплаты, реклама и возвраты по месяцам, ₽",
            body=stacked(
                months,
                {
                    "себестоимость": [float(value) for value in monthly["себестоимость"]],
                    "ФОТ": [float(value) for value in monthly["фот"]],
                    "реклама": [float(value) for value in monthly["реклама"]],
                    "возвраты": [float(value) for value in monthly["возвраты"]],
                },
            ),
        ),
        Block(
            title="Выручка и результат",
            subtitle="₽ по месяцам",
            body=lines(
                months,
                {
                    "выручка": [float(value) for value in monthly["выручка"]],
                    "операционный результат": [float(value) for value in monthly["результат"]],
                },
            ),
        ),
        Block(
            title="Магазины",
            subtitle="за весь период",
            body=table(
                ["Магазин", "Формат", "Выручка", "Валовая прибыль", "ФОТ", "Реклама", "Результат", "Рентабельность"],
                [
                    [
                        str(row["магазин"]),
                        str(row["формат"]),
                        money(float(row["выручка"])),
                        money(float(row["валовая"])),
                        money(float(row["фот"])),
                        money(float(row["реклама"])),
                        money(float(row["результат"])),
                        percent(float(row["результат"]) / float(row["выручка"])),
                    ]
                    for _, row in shops.iterrows()
                ],
                align="ll" + "rrrrrr",
            ),
            note=(
                "Реклама разнесена по магазинам пропорционально выручке: кампании сетевые, привязать их "
                "к конкретной точке нечем. Магазин, у которого результат отрицательный"
                + (f" ({len(losing)} в списке)" if len(losing) else "")
                + ", мог пострадать именно от этого допущения — прежде чем делать выводы, стоит проверить "
                "его отдельно."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины продажи_месяц, персонал_месяц, маркетинг_месяц и возвраты_месяц",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Операционный результат = валовая прибыль − ФОТ − реклама − возвраты. Аренды, налогов "
            "и прочих расходов в данных нет, поэтому это не чистая прибыль."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
