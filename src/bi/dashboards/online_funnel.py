"""Дашборд 8. Самовывоз и доставка: воронка и расхождение источников.

Этот дашборд сделан вокруг неудобного факта. Рекламные кабинеты насчитывают одно число заказов,
касса — другое, и они не сходятся почти вдвое. Обычный выход — показать то число, которое больше
нравится. Здесь оба показаны рядом с разницей, потому что расхождение источников — это и есть
главное, что нужно знать об этой воронке, прежде чем принимать по ней решения.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from bi.dashboards import Dashboard
from bi.render import Block, Card, bars, funnel, grouped_bars, money, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "online_funnel"
TITLE: Final = "Самовывоз и доставка"
FOLDER: Final = "08-воронка"
QUESTION: Final = "Как выглядит путь от рекламного визита до заказа и сходятся ли источники?"
AUDIENCE: Final = "руководитель онлайн-направления"

ONLINE: Final = ("самовывоз", "доставка")

BY_CHANNEL: Final = """
SELECT канал,
       count(DISTINCT чек_id) AS чеков,
       sum(выручка) AS выручка,
       sum(выручка) / nullif(count(DISTINCT чек_id), 0) AS средний_чек,
       sum(количество) / nullif(count(DISTINCT чек_id), 0) AS позиций_в_чеке
FROM продажи_позиции
GROUP BY 1
ORDER BY чеков DESC
"""


def build(store: Store, out: Path) -> Path:
    channels = store.query(BY_CHANNEL)
    ads = store.query(
        """
        SELECT sum(визитов) AS визитов, sum(заказов) AS заказов, sum(расходы) AS расходы
        FROM маркетинг_месяц
        """
    ).iloc[0]

    monthly = store.query(
        """
        SELECT р.месяц, р.заказов, coalesce(к.чеков, 0) AS чеков
        FROM (SELECT месяц, sum(заказов) AS заказов FROM маркетинг_месяц GROUP BY 1) р
        LEFT JOIN (
            SELECT месяц, count(DISTINCT чек_id) AS чеков
            FROM продажи_позиции WHERE канал IN ('самовывоз', 'доставка') GROUP BY 1
        ) к ON CAST(р.месяц AS TIMESTAMP) = к.месяц
        ORDER BY 1
        """
    )

    online = channels[channels["канал"].isin(ONLINE)]
    online_receipts = float(online["чеков"].sum())
    all_receipts = float(channels["чеков"].sum())
    ad_orders = float(ads["заказов"])
    visits = float(ads["визитов"])
    gap = online_receipts - ad_orders

    counter = channels[channels["канал"] == "касса"]
    counter_check = float(counter["средний_чек"].iloc[0]) if len(counter) else 0.0
    online_check = float(online["выручка"].sum() / online_receipts)

    cards = [
        Card(
            "Заказов не через кассу",
            number(online_receipts),
            percent(online_receipts / all_receipts) + " всех чеков",
        ),
        Card("Заказов по данным рекламы", number(ad_orders), f"конверсия из визита {percent(ad_orders / visits, 2)}"),
        Card(
            "Расхождение источников",
            number(gap),
            f"касса видит на {percent(gap / ad_orders)} больше, чем реклама",
            tone="внимание",
        ),
        Card(
            "Средний чек",
            money(online_check, 0),
            f"на кассе {money(counter_check, 0)}",
            tone="хорошо" if online_check >= counter_check else "",
        ),
    ]

    blocks = [
        Block(
            title="Воронка рекламы",
            subtitle="то, что измеряют рекламные кабинеты",
            body=funnel(["визиты", "заказы"], [visits, ad_orders]),
            note=(
                "Дальше этого шага реклама ничего не видит: связать заказ из кабинета с конкретным чеком "
                "нечем — общего идентификатора покупателя в этих данных нет."
            ),
        ),
        Block(
            title="Чеки по каналам",
            subtitle="то, что видит касса",
            body=bars({str(row["канал"]): float(row["чеков"]) for _, row in channels.iterrows()}, horizontal=True),
        ),
        Block(
            title="Реклама против кассы, по месяцам",
            subtitle="заказы по данным рекламы и чеки самовывоза и доставки",
            body=grouped_bars(
                [f"{value:%m.%y}" for value in monthly["месяц"]],
                {
                    "заказы по рекламе": [float(value) for value in monthly["заказов"]],
                    "чеки самовывоза и доставки": [float(value) for value in monthly["чеков"]],
                },
            ),
            note=(
                "Разрыв устойчив во все месяцы, то есть это не сбой выгрузки. Правдоподобное объяснение — "
                "повторные покупатели: человек, однажды пришедший из рекламы, следующий заказ делает "
                "напрямую, и кабинет его уже не считает. Проверить это по имеющимся данным нельзя."
            ),
        ),
        Block(
            title="Каналы продаж",
            body=table(
                ["Канал", "Чеков", "Выручка", "Средний чек", "Позиций в чеке"],
                [
                    [
                        str(row["канал"]),
                        number(float(row["чеков"])),
                        money(float(row["выручка"])),
                        money(float(row["средний_чек"]), 0),
                        number(float(row["позиций_в_чеке"]), 1),
                    ]
                    for _, row in channels.iterrows()
                ],
                align="l" + "rrrr",
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрины продажи_позиции и маркетинг_месяц — два независимых источника",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            "Заказ в рекламном кабинете и чек на кассе — разные события, и складывать их в одну воронку "
            "нельзя. На этой странице они намеренно стоят рядом, а не друг под другом."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
