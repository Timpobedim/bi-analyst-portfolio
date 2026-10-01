"""Дашборд 10. Возвраты: сколько денег уходит обратно и почему.

Возврат — это не только минус выручка, это ещё и сигнал. «Брак» и «истёк срок» указывают на
поставщика и на работу с товаром в магазине, «передумал» и «не подошёл» — на то, как товар описан
и выложен. Поэтому причины здесь не сложены в одно число, а разнесены по магазинам и месяцам.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, lines, money, number, page, percent, stacked, table
from bi.warehouse import Store

NAME: Final = "returns"
TITLE: Final = "Возвраты"
FOLDER: Final = "10-возвраты"
QUESTION: Final = "Сколько выручки возвращается и по каким причинам?"
AUDIENCE: Final = "директор по качеству"

BY_SHOP: Final = """
SELECT м.название AS магазин,
       м.город,
       sum(в.сумма_возвратов) AS сумма,
       sum(в.случаев) AS случаев,
       sum(в.сумма_возвратов) / nullif(п.выручка, 0) AS доля
FROM возвраты_месяц в
JOIN магазины м USING (магазин_id)
JOIN (SELECT магазин_id, sum(выручка) AS выручка FROM продажи_месяц GROUP BY 1) п USING (магазин_id)
GROUP BY 1, 2, п.выручка
ORDER BY доля DESC
"""


def build(store: Store, out: Path) -> Path:
    monthly = store.query(
        """
        SELECT в.месяц,
               sum(в.сумма_возвратов) AS сумма,
               sum(в.случаев) AS случаев,
               sum(в.сумма_возвратов) / nullif(max(п.выручка), 0) AS доля
        FROM возвраты_месяц в
        JOIN (SELECT месяц, sum(выручка) AS выручка FROM продажи_месяц GROUP BY 1) п USING (месяц)
        GROUP BY 1 ORDER BY 1
        """
    )
    reasons = store.query(
        """
        SELECT причина, sum(сумма_возвратов) AS сумма, sum(случаев) AS случаев
        FROM возвраты_месяц GROUP BY 1 ORDER BY сумма DESC
        """
    )
    by_month_reason = store.query(
        """
        SELECT месяц, причина, sum(сумма_возвратов) AS сумма
        FROM возвраты_месяц GROUP BY 1, 2 ORDER BY 1
        """
    )
    shops = store.query(BY_SHOP)

    total = float(reasons["сумма"].sum())
    cases = float(reasons["случаев"].sum())
    revenue = float(store.value("SELECT sum(выручка) FROM продажи_месяц"))
    receipts = float(store.value("SELECT sum(чеков) FROM продажи_месяц"))

    months = [f"{value:%m.%y}" for value in monthly["месяц"]]
    reason_totals = by_month_reason.set_index(["месяц", "причина"])["сумма"]
    stacked_data = {
        str(name): [float(reason_totals.get((month, name), 0.0)) for month in monthly["месяц"]]
        for name in reasons["причина"]
    }

    worst = shops.iloc[0]
    quality = reasons[reasons["причина"].isin(["брак", "истёк срок"])]["сумма"].sum()

    cards = [
        Card("Сумма возвратов", money(total), f"{percent(total / revenue)} выручки"),
        Card("Случаев", number(cases), f"один возврат на {number(receipts / cases, 0)} чеков"),
        Card(
            "Из-за качества",
            percent(float(quality) / total),
            "«брак» и «истёк срок» — зона поставщика и магазина",
            tone="внимание",
        ),
        Card("Худший магазин", str(worst["магазин"]), percent(float(worst["доля"])) + " выручки"),
    ]

    blocks = [
        Block(
            title="Доля возвратов по месяцам",
            subtitle="сумма возвратов к выручке того же месяца",
            body=lines(months, {"доля возвратов": [float(value) for value in monthly["доля"]]}),
        ),
        Block(
            title="Причины по месяцам",
            subtitle="сумма возвратов, ₽",
            body=stacked(months, stacked_data),
        ),
        Block(
            title="Причины",
            body=table(
                ["Причина", "Сумма", "Случаев", "Доля суммы", "Средний возврат"],
                [
                    [
                        str(row["причина"]),
                        money(float(row["сумма"])),
                        number(float(row["случаев"])),
                        percent(float(row["сумма"]) / total),
                        money(float(row["сумма"]) / float(row["случаев"]), 0),
                    ]
                    for _, row in reasons.iterrows()
                ],
                align="l" + "rrrr",
            ),
        ),
        Block(
            title="Магазины",
            subtitle="отсортированы по доле возвратов в своей выручке, а не по сумме",
            body=table(
                ["Магазин", "Город", "Сумма", "Случаев", "Доля выручки"],
                [
                    [
                        str(row["магазин"]),
                        str(row["город"]),
                        money(float(row["сумма"])),
                        number(float(row["случаев"])),
                        percent(float(row["доля"])),
                    ]
                    for _, row in shops.iterrows()
                ],
                align="ll" + "rrr",
            ),
            note=(
                "По сумме первым всегда будет самый крупный магазин — это говорит о его размере, а не "
                "о качестве работы. Доля в собственной выручке сравнима между магазинами разного формата."
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины возвраты_месяц и продажи_месяц",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Возврат отнесён к месяцу продажи, а не к месяцу обращения: так он сравним с выручкой, "
            "из которой возник. Выручка на дашборде продаж возвраты не вычитает."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
