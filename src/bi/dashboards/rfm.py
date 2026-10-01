"""Дашборд 6. RFM: кто покупает, кто вот-вот уйдёт и кто уже ушёл.

Три числа на покупателя — давность последней покупки, частота и деньги — каждое разбито на пять
равных долей. Дальше из этих долей складываются сегменты, с которыми можно что-то делать: чемпионов
удерживают, находящихся под угрозой возвращают, потерянных не трогают, чтобы не жечь бюджет.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, heatmap, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "rfm"
TITLE: Final = "RFM: сегменты покупателей"
FOLDER: Final = "06-rfm"
QUESTION: Final = "Кого удерживать, кого возвращать, а кого уже не трогать?"
AUDIENCE: Final = "руководитель программы лояльности"

SEGMENTS: Final = """
WITH оценки AS (
    SELECT клиент_id,
           давность_дней,
           покупок,
           деньги,
           средний_чек,
           ntile(5) OVER (ORDER BY давность_дней DESC) AS r,
           ntile(5) OVER (ORDER BY покупок) AS f,
           ntile(5) OVER (ORDER BY деньги) AS m
    FROM клиент_итог
)
SELECT *,
       CASE WHEN r >= 4 AND f >= 4 THEN 'Чемпионы'
            WHEN r >= 4 AND f >= 2 THEN 'Лояльные'
            WHEN r >= 4 THEN 'Новички'
            WHEN r = 3 THEN 'Засыпающие'
            WHEN f >= 4 THEN 'Под угрозой'
            ELSE 'Потерянные' END AS сегмент
FROM оценки
"""

ORDER: Final = ("Чемпионы", "Лояльные", "Новички", "Засыпающие", "Под угрозой", "Потерянные")

ADVICE: Final = {
    "Чемпионы": "покупают часто и недавно — держать, а не «активировать» скидкой",
    "Лояльные": "ровная база сети: им интересны новинки и программа лояльности",
    "Новички": "пришли недавно, привычки ещё нет — важна вторая покупка",
    "Засыпающие": "перестали ходить месяц-полтора назад, вернуть ещё дёшево",
    "Под угрозой": "ходили часто, но давно не были — самая дорогая потеря",
    "Потерянные": "редко и давно; массовая рассылка по ним только жжёт бюджет",
}


def build(store: Store, out: Path) -> Path:
    people = store.query(SEGMENTS)
    total = len(people)
    money_total = float(people["деньги"].sum())

    grouped = (
        people.groupby("сегмент")
        .agg(
            клиентов=("клиент_id", "size"),
            деньги=("деньги", "sum"),
            средний_чек=("средний_чек", "mean"),
            давность=("давность_дней", "median"),
            покупок=("покупок", "median"),
        )
        .reset_index()
    )
    grouped["порядок"] = grouped["сегмент"].map({name: index for index, name in enumerate(ORDER)})
    grouped = grouped.sort_values("порядок")

    top_share = float(people.nlargest(max(total // 5, 1), "деньги")["деньги"].sum() / money_total)
    fresh = int((people["давность_дней"] <= 30).sum())
    risky = grouped[grouped["сегмент"] == "Под угрозой"]

    matrix = [
        [
            float(len(people[(people["r"] == r) & (people["f"] == f)]) / total)
            for f in range(1, 6)
        ]
        for r in range(5, 0, -1)
    ]

    cards = [
        Card("Покупателей с картой", number(total), "тех, у кого есть хотя бы одна покупка"),
        Card("Покупали за последние 30 дней", number(fresh), percent(fresh / total) + " базы"),
        Card("Доля денег у верхних 20%", percent(top_share), "если бы все платили поровну, было бы 20%"),
        Card(
            "Под угрозой",
            number(float(risky["клиентов"].iloc[0])) if len(risky) else "0",
            money(float(risky["деньги"].iloc[0])) + " выручки в прошлом" if len(risky) else "",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Сегменты",
            subtitle="и что с каждым делать",
            body=table(
                ["Сегмент", "Клиентов", "Доля", "Деньги", "Медиана покупок", "Дней с покупки", "Что делать"],
                [
                    [
                        str(row["сегмент"]),
                        number(float(row["клиентов"])),
                        percent(float(row["клиентов"]) / total),
                        money(float(row["деньги"])),
                        number(float(row["покупок"])),
                        number(float(row["давность"])),
                        ADVICE[str(row["сегмент"])],
                    ]
                    for _, row in grouped.iterrows()
                ],
                align="l" + "rrrrr" + "l",
            ),
        ),
        Block(
            title="Деньги по сегментам",
            subtitle="сумма покупок за весь период, ₽",
            body=bars({str(row["сегмент"]): float(row["деньги"]) for _, row in grouped.iterrows()}, horizontal=True),
        ),
        Block(
            title="Матрица давности и частоты",
            subtitle="доля всех покупателей в каждой клетке; строки — давность (5 — покупали недавно)",
            body=heatmap(
                [f"R{value}" for value in range(5, 0, -1)],
                [f"F{value}" for value in range(1, 6)],
                matrix,
            ),
            note=(
                "Клетки не равны по 4%, хотя оценки нарезаны на равные пятые части: давность и частота "
                "связаны — кто ходит часто, тот и был недавно."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина клиент_итог",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Давность считается от последнего дня данных, а не от сегодняшней даты: витрина не обязана "
            "стареть между пересборками."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
