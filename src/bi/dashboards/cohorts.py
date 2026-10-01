"""Дашборд 7. Когорты: возвращаются ли покупатели и стало ли лучше.

Когорта — все, кто впервые купил в один месяц. Дальше смотрим, какая их доля приходила через месяц,
через два, через полгода. Это единственный способ отличить «стало больше покупателей» от «стало
больше новых покупателей вместо ушедших»: по общему числу активных клиентов эти две истории выглядят
одинаково.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from bi.dashboards import Dashboard
from bi.render import Block, Card, heatmap, lines, number, page, percent, table
from bi.warehouse import Store

NAME: Final = "cohorts"
TITLE: Final = "Когорты и удержание"
FOLDER: Final = "07-когорты"
QUESTION: Final = "Возвращаются ли покупатели после первой покупки?"
AUDIENCE: Final = "руководитель программы лояльности"

DEPTH: Final = 12
"""Сколько месяцев жизни когорты показываем: дальше у молодых когорт всё равно нет данных."""

RETENTION: Final = """
WITH первая AS (
    SELECT клиент_id, date_trunc('month', CAST(min(дата) AS TIMESTAMP)) AS когорта
    FROM продажи_позиции GROUP BY 1
),
активность AS (
    SELECT DISTINCT клиент_id, месяц FROM продажи_позиции
)
SELECT п.когорта,
       date_diff('month', п.когорта, а.месяц) AS смещение,
       count(DISTINCT а.клиент_id) AS клиентов
FROM первая п JOIN активность а USING (клиент_id)
GROUP BY 1, 2
ORDER BY 1, 2
"""


def build(store: Store, out: Path) -> Path:
    frame = store.query(RETENTION)
    starts = frame[frame["смещение"] == 0].set_index("когорта")["клиентов"]
    sizes: dict[object, float] = dict(zip(starts.index, starts.to_numpy(dtype=float), strict=True))
    wide = frame.pivot(index="когорта", columns="смещение", values="клиентов").reindex(columns=range(DEPTH + 1))
    share = wide.div(starts, axis=0)

    labels = [f"{value:%m.%Y}" for value in share.index]
    matrix: list[list[float | None]] = [
        [None if pd.isna(value) else float(value) for value in row] for row in share.to_numpy()
    ]

    # Средняя кривая удержания: по каждому смещению берём только когорты, которые до него дожили.
    curve = [float(share[offset].dropna().mean()) for offset in range(DEPTH + 1)]
    mature = share[share[3].notna()]
    third = float(mature[3].mean()) if len(mature) else 0.0
    sixth = float(share[6].dropna().mean()) if share[6].notna().any() else 0.0

    first_half = share[share.index < share.index[len(share) // 2]]
    second_half = share[share.index >= share.index[len(share) // 2]]
    early = float(first_half[3].dropna().mean()) if first_half[3].notna().any() else 0.0
    late = float(second_half[3].dropna().mean()) if second_half[3].notna().any() else 0.0

    cards = [
        Card("Когорт в данных", number(len(share)), "по месяцу первой покупки"),
        Card("Первая когорта", f"{share.index[0]:%m.%Y}", number(sizes[share.index[0]]) + " человек"),
        Card("Возвращаются на 3-й месяц", percent(third), "в среднем по дожившим когортам"),
        Card(
            "На 6-й месяц",
            percent(sixth),
            "позже кривая почти не падает" if sixth > 0 else "",
            tone="хорошо" if sixth >= 0.4 else "",
        ),
    ]

    blocks = [
        Block(
            title="Удержание по когортам",
            subtitle="доля когорты, купившая через N месяцев после первой покупки",
            body=heatmap(labels, [f"{offset}" for offset in range(DEPTH + 1)], matrix),
            note=(
                "Пустые клетки — не ноль, а «столько ещё не прошло»: когорта прошлого месяца просто "
                "не могла дожить до шестого. Сравнивать когорты между собой можно только по общим столбцам."
            ),
        ),
        Block(
            title="Средняя кривая удержания",
            subtitle="по всем когортам, доля от первого месяца",
            body=lines([f"{offset} мес" for offset in range(DEPTH + 1)], {"доля вернувшихся": curve}),
            note=(
                "Провал между нулевым и первым месяцем есть всегда: в нулевом месяце когорта по "
                "определению активна на 100%, это не удержание, а способ её сборки."
            ),
        ),
        Block(
            title="Размеры когорт",
            body=table(
                ["Когорта", "Человек", "1-й месяц", "3-й месяц", "6-й месяц", "12-й месяц"],
                [
                    [
                        f"{index:%m.%Y}",
                        number(sizes.get(index, 0.0)),
                        _cell(matrix[position], 1),
                        _cell(matrix[position], 3),
                        _cell(matrix[position], 6),
                        _cell(matrix[position], 12),
                    ]
                    for position, index in enumerate(share.index)
                ],
                align="l" + "rrrrr",
            ),
        ),
    ]

    html = page(
        title=TITLE,
        question=QUESTION,
        cards=cards,
        blocks=blocks,
        source="витрина продажи_позиции",
        prepared_on=datetime.now(UTC).date(),
        metrics_note=(
            f"Удержание на 3-й месяц у ранних когорт {percent(early)}, у поздних {percent(late)} — "
            "сравнивать имеет смысл только эти два числа, а не когорты разного возраста."
        ),
    )
    path = out / FOLDER / "дашборд.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path


def _cell(row: Sequence[float | None], offset: int) -> str:
    """Доля когорты на N-м месяце жизни; прочерк значит, что когорта до него ещё не дожила."""
    value = row[offset] if offset < len(row) else None
    return "—" if value is None else percent(value)


DASHBOARD: Final = Dashboard(
    name=NAME, title=TITLE, folder=FOLDER, question=QUESTION, audience=AUDIENCE, build=build
)
