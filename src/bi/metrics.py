"""Единый словарь метрик: одно определение — одна формула — один смысл.

Это главное, чего не хватает почти любому BI-портфолио. Меры живут внутри файла отчёта: в `.pbix`
они спрятаны в бинарном слое, в дашборде — в настройках виджета. Через полгода «выручка» на экране
продаж и «выручка» на экране маркетинга расходятся, и никто не может объяснить, почему.

Здесь определения лежат в одном месте, у каждой метрики написано, что именно она считает и чего
не учитывает, а витрины и дашборды берут формулу отсюда, а не пишут свою.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Metric:
    """Метрика: как считается, что означает и чего в ней нет."""

    key: str
    name: str
    formula: str
    definition: str
    unit: str
    caveat: str = ""

    def line(self) -> str:
        return f"{self.name} ({self.unit}): {self.definition}"


CATALOG: Final[tuple[Metric, ...]] = (
    Metric(
        key="revenue",
        name="Выручка",
        formula="sum(позиции.количество * позиции.цена)",
        definition="сумма проданного по цене чека, то есть уже со скидкой",
        unit="₽",
        caveat="возвраты не вычтены — для очищенной величины есть «Чистая выручка»",
    ),
    Metric(
        key="net_revenue",
        name="Чистая выручка",
        formula="Выручка − Сумма возвратов",
        definition="выручка за вычетом возвращённого товара",
        unit="₽",
        caveat="возврат относится к дате возврата, а не к дате покупки",
    ),
    Metric(
        key="cost",
        name="Себестоимость",
        formula="sum(позиции.количество * товары.себестоимость)",
        definition="закупочная стоимость проданного товара",
        unit="₽",
    ),
    Metric(
        key="margin",
        name="Валовая прибыль",
        formula="Выручка − Себестоимость",
        definition="сколько осталось с продаж до расходов на магазины и рекламу",
        unit="₽",
    ),
    Metric(
        key="margin_share",
        name="Маржинальность",
        formula="Валовая прибыль / Выручка",
        definition="доля валовой прибыли в выручке",
        unit="%",
    ),
    Metric(
        key="receipts",
        name="Чеков",
        formula="count(distinct чеки.чек_id)",
        definition="число покупок, а не число товаров",
        unit="шт",
    ),
    Metric(
        key="average_receipt",
        name="Средний чек",
        formula="Выручка / Чеков",
        definition="сколько в среднем оставляет покупатель за одну покупку",
        unit="₽",
        caveat="среднее чувствительно к крупным закупкам; для сравнения магазинов честнее медиана",
    ),
    Metric(
        key="items_per_receipt",
        name="Позиций в чеке",
        formula="sum(позиции.количество) / Чеков",
        definition="сколько товаров покупают за раз",
        unit="шт",
    ),
    Metric(
        key="plan_completion",
        name="Выполнение плана",
        formula="Выручка / План выручки",
        definition="какую долю месячного плана магазин закрыл",
        unit="%",
        caveat="в месяц ремонта магазин закрыт, и невыполнение плана — не работа команды",
    ),
    Metric(
        key="return_rate",
        name="Доля возвратов",
        formula="Сумма возвратов / Выручка",
        definition="какая часть проданного вернулась",
        unit="%",
    ),
    Metric(
        key="lfl",
        name="Сопоставимые продажи (LFL)",
        formula="Выручка текущего периода / Выручка того же периода год назад − 1",
        definition="рост по магазинам, которые работали в обоих периодах",
        unit="%",
        caveat="магазины, открытые меньше года назад, в расчёт не входят — иначе рост сети приписывается старым точкам",
    ),
    Metric(
        key="romi",
        name="Окупаемость рекламы (ROMI)",
        formula="(Выручка с канала − Расходы канала) / Расходы канала",
        definition="сколько рубль рекламы приносит сверх себя",
        unit="%",
        caveat="выручка канала считается по последнему клику и переоценивает прямые каналы",
    ),
    Metric(
        key="cac",
        name="Стоимость заказа",
        formula="Расходы канала / Заказов с канала",
        definition="во сколько обходится один заказ из канала",
        unit="₽",
    ),
    Metric(
        key="turnover",
        name="Оборачиваемость",
        formula="Себестоимость проданного за месяц / Средний остаток",
        definition="сколько раз за месяц обновился запас",
        unit="раз",
        caveat="остатки берутся на первое число месяца — это приближение",
    ),
    Metric(
        key="revenue_per_employee",
        name="Выручка на сотрудника",
        formula="Выручка магазина / Число работавших сотрудников",
        definition="сколько приносит один человек в месяц",
        unit="₽",
    ),
    Metric(
        key="turnover_staff",
        name="Текучесть",
        formula="Уволенные за период / Среднесписочная численность",
        definition="какая доля коллектива сменилась",
        unit="%",
    ),
    Metric(
        key="retention",
        name="Возвращаемость",
        formula="Клиенты когорты, купившие в месяце N / Размер когорты",
        definition="какая доля покупателей вернулась через N месяцев",
        unit="%",
    ),
)

BY_KEY: Final = {metric.key: metric for metric in CATALOG}


def metric(key: str) -> Metric:
    """Метрика по ключу; неизвестный ключ — ошибка, а не тихий ноль."""
    found = BY_KEY.get(key)
    if found is None:
        known = ", ".join(sorted(BY_KEY))
        raise KeyError(f"Метрики «{key}» нет в словаре. Есть: {known}")
    return found


def table() -> tuple[list[str], list[list[str]]]:
    """Словарь метрик таблицей — он попадает и в отчёт, и на страницу дашборда."""
    headers = ["Метрика", "Единица", "Формула", "Что означает", "Чего не учитывает"]
    rows = [
        [item.name, item.unit, item.formula, item.definition, item.caveat or "—"] for item in CATALOG
    ]
    return headers, rows
