"""Реестр дашбордов: тринадцать страниц, собранных из одних и тех же витрин.

У каждого дашборда один вопрос и один адресат. Это важнее, чем кажется: дашборд «обо всём» никто
не открывает дважды, потому что на нём невозможно найти ответ. Поэтому здесь тринадцать отдельных
страниц — продажи, товары, клиенты, маркетинг, склад, персонал, финансы и качество данных, — и
каждая начинается с вопроса, на который отвечает.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bi.warehouse import Store

Builder = Callable[[Store, Path], Path]


@dataclass(frozen=True, slots=True)
class Dashboard:
    """Один дашборд: имя для команды, папка для результата и функция сборки."""

    name: str
    title: str
    folder: str
    question: str
    audience: str
    build: Builder


def registry() -> tuple[Dashboard, ...]:
    """Все дашборды по порядку. Импорт внутри функции — чтобы список не тянул лишнего."""
    from bi.dashboards import (
        abc,
        cohorts,
        data_quality,
        finance,
        margin,
        marketing,
        online_funnel,
        plan_fact,
        returns,
        rfm,
        sales,
        staff,
        stock,
        stores,
    )

    return (
        sales.DASHBOARD,
        plan_fact.DASHBOARD,
        stores.DASHBOARD,
        abc.DASHBOARD,
        margin.DASHBOARD,
        rfm.DASHBOARD,
        cohorts.DASHBOARD,
        online_funnel.DASHBOARD,
        marketing.DASHBOARD,
        returns.DASHBOARD,
        stock.DASHBOARD,
        staff.DASHBOARD,
        finance.DASHBOARD,
        data_quality.DASHBOARD,
    )


def find(name: str) -> Dashboard | None:
    return next((dashboard for dashboard in registry() if dashboard.name == name), None)
