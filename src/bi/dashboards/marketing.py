"""Дашборд 9. Каналы привлечения: куда уходят деньги и что они приносят.

Здесь важнее обычного понимать, откуда берутся числа. Расходы, визиты и заказы — из рекламных
кабинетов, это измеренные величины. А вот «выручка канала» ничем не измерена: выручка сети
разнесена по каналам пропорционально числу заказов. Поэтому окупаемость на этой странице — оценка,
и подписана она именно так, а не как факт.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, grouped_bars, lines, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "marketing"
TITLE: Final = "Каналы привлечения"
FOLDER: Final = "09-маркетинг"
QUESTION: Final = "Какие каналы привлечения окупаются, а какие только тратят бюджет?"
AUDIENCE: Final = "руководитель маркетинга"

BY_CHANNEL: Final = """
SELECT канал,
       sum(визитов) AS визитов,
       sum(заказов) AS заказов,
       sum(расходы) AS расходы,
       sum(выручка_канала) AS выручка,
       sum(заказов) * 1.0 / nullif(sum(визитов), 0) AS конверсия,
       sum(расходы) / nullif(sum(заказов), 0) AS стоимость_заказа,
       sum(расходы) / nullif(sum(выручка_канала), 0) AS доля_расходов
FROM маркетинг_месяц
GROUP BY 1
ORDER BY расходы DESC
"""


def build(store: Store, out: Path) -> Path:
    channels = store.query(BY_CHANNEL)
    monthly = store.query(
        """
        SELECT месяц, sum(расходы) AS расходы, sum(заказов) AS заказов,
               sum(расходы) / nullif(sum(заказов), 0) AS стоимость_заказа
        FROM маркетинг_месяц GROUP BY 1 ORDER BY 1
        """
    )
    per_channel_month = store.query(
        """
        SELECT месяц, канал, расходы / nullif(заказов, 0) AS стоимость_заказа
        FROM маркетинг_месяц ORDER BY месяц
        """
    )

    spend = float(channels["расходы"].sum())
    orders = float(channels["заказов"].sum())
    visits = float(channels["визитов"].sum())
    cheapest = channels.sort_values("стоимость_заказа").iloc[0]
    dearest = channels.sort_values("стоимость_заказа").iloc[-1]

    months = [f"{value:%m.%y}" for value in monthly["месяц"]]
    names = list(channels["канал"])
    cost_series = {
        name: [
            float(value)
            for value in per_channel_month[per_channel_month["канал"] == name]
                .sort_values("месяц")["стоимость_заказа"]
                .fillna(0.0)
        ]
        for name in names
    }

    cards = [
        Card("Расходы на привлечение", money(spend), "за весь период"),
        Card("Заказов из рекламы", number(orders), f"конверсия из визита {percent(orders / visits, 2)}"),
        Card("Стоимость заказа", money(spend / orders, 0), "в среднем по всем каналам"),
        Card(
            "Разброс между каналами",
            f"{money(float(cheapest['стоимость_заказа']), 0)} … {money(float(dearest['стоимость_заказа']), 0)}",
            f"дешевле всего «{cheapest['канал']}», дороже всего «{dearest['канал']}»",
            tone="внимание",
        ),
    ]

    blocks = [
        Block(
            title="Каналы",
            subtitle="за весь период",
            body=table(
                ["Канал", "Визитов", "Заказов", "Конверсия", "Расходы", "Стоимость заказа", "Доля расходов в выручке"],
                [
                    [
                        str(row["канал"]),
                        number(float(row["визитов"])),
                        number(float(row["заказов"])),
                        percent(float(row["конверсия"]), 2),
                        money(float(row["расходы"])),
                        money(float(row["стоимость_заказа"]), 0),
                        percent(float(row["доля_расходов"])),
                    ]
                    for _, row in channels.iterrows()
                ],
                align="l" + "rrrrrr",
            ),
            note=(
                "Последний столбец — расходы канала к разнесённой на него выручке. Это оценка «сколько "
                "рекламы приходится на рубль выручки», а не измеренная окупаемость."
            ),
        ),
        Block(
            title="Расходы и заказы по месяцам",
            subtitle="масштабы разные, поэтому смотреть надо на форму, а не на высоту",
            body=grouped_bars(
                months,
                {
                    "расходы, ₽": [float(value) for value in monthly["расходы"]],
                    "заказов": [float(value) for value in monthly["заказов"]],
                },
            ),
            note=(
                "Два ряда на одной шкале сведены здесь намеренно и честно проиграны: столбик заказов "
                "рядом с расходами почти не виден. Рисовать им вторую ось было бы хуже — на графике "
                "с двумя осями любые две линии можно свести так, чтобы они «совпали»."
            ),
        ),
        Block(
            title="Стоимость заказа по каналам",
            subtitle="₽ за заказ, по месяцам",
            body=lines(months, cost_series),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина маркетинг_месяц (расходы и визиты — рекламные кабинеты, выручка — разнесена)",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Выручка канала не измерена: это выручка сети, разнесённая пропорционально числу заказов. "
            "Настоящая атрибуция требует сквозной идентификации покупателя, которой в этих данных нет."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
