"""Склад данных розничной сети: десять таблиц, из которых растут все витрины.

Один источник на все тринадцать дашбордов — это принципиально. В портфолио обычно наоборот: каждый
дашборд сделан на своём наборе, и вопрос «почему выручка на двух экранах разная» просто не возникает,
потому что экраны никак не связаны. Здесь связь есть, и расхождение чисел между дашбордами было бы
ошибкой, которую видно.

Данные воспроизводимы по зерну и намеренно неидеальны: есть возвраты, пропуски в справочнике,
скидки и месяц, когда один магазин стоял на ремонте.

Всё считается массивами numpy, а не циклами по строкам. Первая версия этого модуля создавала чеки
и позиции обычным циклом с обращением `products.loc[...]` внутри — на полутора миллионах строк она
не досчиталась за десять минут. Тот же объём в векторном виде готовится за пару секунд.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import numpy as np
import pandas as pd

SEED: Final = 42
START: Final = date(2024, 9, 1)
DAYS: Final = 730
"""Ровно двадцать четыре полных месяца, последний из них — август 2026 года.

Двадцать четыре, а не «примерно два года», по двум причинам. Сопоставимые продажи сравнивают
последние двенадцать месяцев с предыдущими двенадцатью: если в данных двадцать два месяца, в базу
сравнения попадает восемь, и рост выходит выдуманным. А период, оборванный посреди месяца, даёт
в каждом графике времени последний столбец вдвое ниже соседнего — не потому, что упали продажи,
а потому, что месяц ещё не кончился.
"""

CITIES: Final = ("Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Краснодар")
FORMATS: Final = ("гипермаркет", "супермаркет", "у дома")
CATEGORIES: Final = {
    "молочное": (0.22, 0.28),
    "бакалея": (0.2, 0.37),
    "мясо и рыба": (0.16, 0.25),
    "овощи и фрукты": (0.14, 0.31),
    "напитки": (0.12, 0.46),
    "бытовая химия": (0.09, 0.52),
    "детское": (0.07, 0.43),
}
"""Категория: доля в продажах и наценка.

Наценка, а не маржа: наценка 0,28 даёт маржинальность 0,28 / 1,28 ≈ 22%. Вместе эти семь строк
дают по сети около 26% валовой маржи — столько и бывает в продуктовой рознице. В первой версии
наценки были вдвое ниже, маржа выходила 16%, и на дашборде финансов зарплаты съедали всю прибыль.
"""

CHANNELS: Final = {
    # канал: (доля визитов, стоимость визита, конверсия)
    "поиск": (0.32, 12.0, 0.031),
    "маркетплейс": (0.24, 6.0, 0.052),
    "соцсети": (0.18, 7.0, 0.019),
    "рассылка": (0.14, 1.5, 0.061),
    "наружная реклама": (0.12, 9.0, 0.008),
}
"""Стоимость визита подобрана так, чтобы стоимость заказа получалась осмысленной.

Заказ стоит «цена визита / конверсия»: у рассылки это 25 ₽, у поиска — около 390 ₽, у наружной
рекламы — больше тысячи. Последнее не ошибка: наружная реклама работает на узнавание, и по заказам
она не окупается никогда. Раньше стоимость визита была вчетверо выше, и средний заказ обходился
дороже среднего чека — то есть реклама не окупалась в принципе, чего в работающей сети не бывает.
"""

VISITS_PER_MONTH: Final = 150_000
"""Визитов по всем каналам за месяц; вместе со стоимостью визита даёт около 2,7% выручки на рекламу."""
POSITIONS: Final = ("продавец", "кассир", "товаровед", "директор магазина")
SALARIES: Final = {"продавец": 58_000, "кассир": 54_000, "товаровед": 72_000, "директор магазина": 115_000}
RETURN_REASONS: Final = ("брак", "не подошёл", "истёк срок", "передумал")
SUPPORT_TOPICS: Final = ("цена на кассе", "качество товара", "работа персонала", "доставка", "программа лояльности")
SALE_CHANNELS: Final = ("касса", "самовывоз", "доставка")

SHOPS: Final = 12
PRODUCTS: Final = 900
CUSTOMERS: Final = 9_000
STOCK_PRODUCTS: Final = 200

RECEIPTS_PER_DAY: Final = 90.0
"""Чеков в день у магазина среднего формата; у дома примерно 55, у гипермаркета около 230.

Это главный масштабный параметр всего склада, и подобран он не «чтобы красиво». Если поставить
меньше, магазин начинает делать несколько сотен тысяч рублей в месяц — и тогда фонд оплаты труда
оказывается больше выручки, а дашборд финансов показывает сети убыток, которого не бывает
у работающей розницы. Проверять такие вещи надо на витринах, а не на глаз: несогласованность
между продажами и зарплатами видна только тогда, когда они сведены в один отчёт.
"""

SIZE_FACTOR: Final = {"гипермаркет": 2.6, "супермаркет": 1.4, "у дома": 0.6}

STAFF_BY_FORMAT: Final = {"гипермаркет": 17, "супермаркет": 9, "у дома": 4}
"""Сколько человек держит магазин каждого формата: численность идёт за размером, а не берётся случайно."""

STAFF_TENURE: Final = (240, 1_400)
"""Сколько дней человек работает на одном месте до ухода: в рознице это от восьми месяцев до трёх лет."""

STOCK_COVER: Final = 0.8
"""Запас в долях месячных продаж: примерно на три недели, то есть оборачиваемость около 1,25 раза."""

CUSTOMERS_AT_START: Final = 0.35
"""Доля покупателей, у которых карта была заведена ещё до начала периода."""

CUSTOMER_LIFETIME: Final = (6.1, 0.55)
"""Логнормальный срок жизни карты в днях: медиана — около пятнадцати месяцев."""

CUSTOMER_FREQUENCY_SPREAD: Final = 1.3
"""Разброс частоты покупок между людьми: кто-то заходит через день, кто-то раз в квартал.

Без этого разброса удержание по когортам выходит плоским: сто процентов месяц за месяцем, пока
покупатель не ушёл насовсем, — и обрыв. Настоящая кривая удержания падает постепенно именно
потому, что редкий покупатель в отдельно взятом месяце может просто не зайти, не переставая
при этом быть клиентом.
"""

REPAIR_SHOP: Final = 3
REPAIR_MONTH: Final = date(2026, 2, 1)
"""Один магазин месяц стоял на ремонте: витрины обязаны это показывать, а не прятать.

Месяц выбран внутри последнего года намеренно. Так простой попадает в текущий период
сопоставимых продаж и портит их этому магазину — а отличить «магазин работает хуже» от
«магазин не работал» и есть та задача, ради которой сопоставимые продажи считают.
"""

LATE_SHOP: Final = 12
LATE_OPENING: Final = date(2025, 11, 5)
"""Сеть растёт: двенадцатый магазин открылся посреди периода, и сравнивать ему пока не с чем."""


@dataclass(frozen=True, slots=True)
class Warehouse:
    """Все таблицы склада разом."""

    магазины: pd.DataFrame
    товары: pd.DataFrame
    сотрудники: pd.DataFrame
    чеки: pd.DataFrame
    позиции: pd.DataFrame
    возвраты: pd.DataFrame
    план: pd.DataFrame
    маркетинг: pd.DataFrame
    остатки: pd.DataFrame
    обращения: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "магазины": self.магазины,
            "товары": self.товары,
            "сотрудники": self.сотрудники,
            "чеки": self.чеки,
            "позиции": self.позиции,
            "возвраты": self.возвраты,
            "план": self.план,
            "маркетинг": self.маркетинг,
            "остатки": self.остатки,
            "обращения": self.обращения,
        }


def generator(seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng(seed)


def build(seed: int = SEED) -> Warehouse:
    """Собирает весь склад: справочники, продажи, план, маркетинг, остатки и обращения."""
    rng = generator(seed)
    магазины = _shops(rng)
    товары = _products(rng)
    сотрудники = _staff(rng, магазины)
    чеки, позиции = _sales(rng, магазины, товары)
    возвраты = _returns(rng, позиции)
    план = _plan(rng, чеки, позиции)
    маркетинг = _marketing(rng)
    остатки = _stock(rng, магазины, товары, чеки, позиции)
    обращения = _support(rng, магазины)
    return Warehouse(
        магазины=магазины,
        товары=товары,
        сотрудники=сотрудники,
        чеки=чеки,
        позиции=позиции,
        возвраты=возвраты,
        план=план,
        маркетинг=маркетинг,
        остатки=остатки,
        обращения=обращения,
    )


def _shops(rng: np.random.Generator) -> pd.DataFrame:
    city = rng.choice(CITIES, size=SHOPS)
    shop_format = rng.choice(FORMATS, size=SHOPS, p=[0.25, 0.45, 0.3])
    area = np.select(
        [shop_format == "гипермаркет", shop_format == "супермаркет", shop_format == "у дома"],
        [rng.normal(4_200, 700, SHOPS), rng.normal(1_100, 220, SHOPS), rng.normal(320, 70, SHOPS)],
        default=800.0,
    )
    opened = [START - timedelta(days=int(value)) for value in rng.integers(200, 2_800, size=SHOPS)]
    opened[LATE_SHOP - 1] = LATE_OPENING
    return pd.DataFrame(
        {
            "магазин_id": np.arange(1, SHOPS + 1),
            "название": [f"«{city[index]}-{index + 1}»" for index in range(SHOPS)],
            "город": city,
            "формат": shop_format,
            "площадь": np.round(np.clip(area, 120, 6_000), 0),
            "открыт": opened,
        }
    )


def _products(rng: np.random.Generator) -> pd.DataFrame:
    names = list(CATEGORIES)
    category = rng.choice(names, size=PRODUCTS, p=[CATEGORIES[name][0] for name in names])
    markup = np.array([CATEGORIES[name][1] for name in category])
    cost = np.round(np.clip(rng.lognormal(4.4, 0.75, PRODUCTS), 12, 9_000), 2)
    price = np.round(cost * (1 + markup + rng.normal(0, 0.04, PRODUCTS)), 2)
    frame = pd.DataFrame(
        {
            "товар_id": np.arange(1, PRODUCTS + 1),
            "название": [f"Товар {number}" for number in range(1, PRODUCTS + 1)],
            "категория": category,
            "поставщик": rng.choice([f"Поставщик {letter}" for letter in "АБВГДЕЖЗ"], size=PRODUCTS),
            "себестоимость": cost,
            "цена": np.maximum(price, cost * 1.02).round(2),
        }
    )
    # В справочнике у части позиций не заполнен поставщик — обычное дело в живой базе.
    missing = rng.choice(PRODUCTS, size=int(PRODUCTS * 0.03), replace=False)
    frame.loc[frame.index[missing], "поставщик"] = None
    return frame


def _staff(rng: np.random.Generator, shops: pd.DataFrame) -> pd.DataFrame:
    """Штат магазинов: рабочие места, а не разовый список людей.

    Первая версия заводила фиксированный список сотрудников и часть из них увольняла. Численность
    от этого могла только убывать: замен никто не нанимал. На дашборде персонала это давало сразу
    две неправды — падающий штат при растущей выручке и, как следствие, выработку на сотрудника,
    которая росла сама собой. Здесь у магазина есть рабочие места, и когда человек уходит, место
    занимает следующий; отсюда же берётся честная текучесть.
    """
    finish = START + timedelta(days=DAYS)
    места = np.maximum(rng.poisson([STAFF_BY_FORMAT[str(value)] for value in shops["формат"]]), 2)

    магазины: list[int] = []
    должности: list[str] = []
    приняты: list[date] = []
    уволены: list[date | None] = []

    for магазин, открыт, сколько in zip(shops["магазин_id"], shops["открыт"], места, strict=True):
        for _ in range(int(сколько)):
            должность = str(rng.choice(POSITIONS, p=[0.45, 0.3, 0.18, 0.07]))
            момент = max(открыт, START - timedelta(days=int(rng.integers(0, 1_500))))
            while момент < finish:
                уход = момент + timedelta(days=int(rng.integers(*STAFF_TENURE)))
                магазины.append(int(магазин))
                должности.append(должность)
                приняты.append(момент)
                уволены.append(None if уход >= finish else уход)
                if уход >= finish:
                    break
                момент = уход

    оклады = np.array([SALARIES[name] for name in должности], dtype=float)
    return pd.DataFrame(
        {
            "сотрудник_id": np.arange(1, len(магазины) + 1),
            "магазин_id": магазины,
            "должность": должности,
            "принят": приняты,
            "уволен": уволены,
            "оклад": np.round(оклады * rng.normal(1, 0.07, len(магазины)), 2),
        }
    )


def _months() -> np.ndarray:
    """Месяцы периода — ровно те же, что и в продажах.

    Раньше маркетинг и остатки брали `DAYS // 30` месяцев, то есть двадцать один при двадцати двух
    в продажах. Ошибка тихая: последний месяц просто отсутствовал в этих таблицах, и дашборд
    маркетинга молча показывал период короче, чем дашборд продаж.
    """
    return pd.date_range(START, START + timedelta(days=DAYS - 1), freq="MS").date


def _customer_column(rng: np.random.Generator, receipt_day: np.ndarray, total: int) -> np.ndarray:
    """Кому принадлежит каждый чек: покупатели приходят и уходят, а не живут вечно.

    Если выбирать клиента равномерно из всего списка, как было в первой версии, то в первый же
    месяц засветятся почти все девять тысяч: когорта получается одна на весь период, удержание
    в ней около ста процентов, и когортный анализ теряет смысл. Поэтому у каждого покупателя есть
    день, когда он завёл карту, и срок, после которого он ей пользоваться перестал.
    """
    base = int(CUSTOMERS * CUSTOMERS_AT_START)
    joined = np.concatenate([np.zeros(base, dtype=int), rng.integers(0, DAYS, size=CUSTOMERS - base)])
    lifetime = np.maximum(rng.lognormal(*CUSTOMER_LIFETIME, size=CUSTOMERS).astype(int), 30)
    left = joined + lifetime
    частота = rng.lognormal(0.0, CUSTOMER_FREQUENCY_SPREAD, size=CUSTOMERS)

    column = np.empty(total, dtype=np.int64)
    cursor = 0
    # Чеки уже идут по дням подряд, поэтому хватает одного прохода по календарю, а не по строкам.
    for day, count in enumerate(np.bincount(receipt_day, minlength=DAYS)):
        if not count:
            continue
        active = np.flatnonzero((joined <= day) & (left > day))
        веса = частота[active]
        column[cursor : cursor + int(count)] = rng.choice(active, size=int(count), p=веса / веса.sum()) + 1
        cursor += int(count)
    return column


def _sales(rng: np.random.Generator, shops: pd.DataFrame, products: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Чеки и позиции целиком в массивах: сезонность, выходные и ремонт заложены в интенсивность."""
    days = np.arange(DAYS)
    calendar = [START + timedelta(days=int(value)) for value in days]
    season = 1 + 0.18 * np.sin(2 * np.pi * days / 365) + 0.0004 * days
    weekend = np.array([1.22 if moment.weekday() >= 5 else 1.0 for moment in calendar])

    shop_ids = shops["магазин_id"].to_numpy()
    size = np.array([SIZE_FACTOR[str(value)] for value in shops["формат"]])

    # Сетка «день × магазин», развёрнутая в один ряд.
    grid_day = np.repeat(days, len(shop_ids))
    grid_shop = np.tile(shop_ids, DAYS)
    intensity = RECEIPTS_PER_DAY * np.repeat(season * weekend, len(shop_ids)) * np.tile(size, DAYS)

    repair = np.array(
        [moment.year == REPAIR_MONTH.year and moment.month == REPAIR_MONTH.month for moment in calendar]
    )
    closed = np.repeat(repair, len(shop_ids)) & (grid_shop == REPAIR_SHOP)
    # До дня открытия магазин не торгует: иначе у новой точки появится история, которой не было.
    opening = np.array([(moment - START).days for moment in shops["открыт"]])
    not_open_yet = grid_day < np.tile(opening, DAYS)
    counts = rng.poisson(np.maximum(intensity, 0.2))
    counts[closed | not_open_yet] = 0

    receipt_day = np.repeat(grid_day, counts)
    receipt_shop = np.repeat(grid_shop, counts)
    total = int(receipt_day.size)
    receipts = pd.DataFrame(
        {
            "чек_id": np.arange(1, total + 1),
            "дата": [calendar[int(value)] for value in receipt_day],
            "магазин_id": receipt_shop,
            "клиент_id": _customer_column(rng, receipt_day, total),
            "канал": rng.choice(SALE_CHANNELS, size=total, p=[0.72, 0.17, 0.11]),
        }
    )

    weights = np.array([CATEGORIES[str(name)][0] for name in products["категория"]], dtype=float)
    weights = weights / weights.sum()
    product_ids = products["товар_id"].to_numpy()
    price_by_id = np.zeros(int(product_ids.max()) + 1, dtype=float)
    price_by_id[product_ids] = products["цена"].to_numpy()

    per_receipt = rng.integers(1, 6, size=total)
    line_receipt = np.repeat(receipts["чек_id"].to_numpy(), per_receipt)
    line_count = int(line_receipt.size)
    product = rng.choice(product_ids, size=line_count, p=weights)
    discount = rng.choice([0.0, 0.0, 0.0, 0.05, 0.1, 0.2], size=line_count, p=[0.55, 0.15, 0.1, 0.1, 0.07, 0.03])

    lines = pd.DataFrame(
        {
            "чек_id": line_receipt,
            "товар_id": product,
            "количество": rng.integers(1, 4, size=line_count),
            "цена": np.round(price_by_id[product] * (1 - discount), 2),
            "скидка": discount,
        }
    )
    return receipts, lines


def _returns(rng: np.random.Generator, lines: pd.DataFrame) -> pd.DataFrame:
    taken = lines.sample(frac=0.017, random_state=7)
    return pd.DataFrame(
        {
            "чек_id": taken["чек_id"].to_numpy(),
            "товар_id": taken["товар_id"].to_numpy(),
            "количество": 1,
            "причина": rng.choice(RETURN_REASONS, size=len(taken), p=[0.34, 0.3, 0.22, 0.14]),
        }
    )


def _plan(rng: np.random.Generator, receipts: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """План ставится «от достигнутого» с амбицией: иногда выполним, иногда нет."""
    sums = lines.assign(сумма=lines["количество"] * lines["цена"]).groupby("чек_id", as_index=False)["сумма"].sum()
    merged = receipts.merge(sums, on="чек_id", how="left")
    merged["месяц"] = [момент.replace(day=1) for момент in merged["дата"]]
    actual = merged.groupby(["месяц", "магазин_id"], as_index=False)["сумма"].sum()
    # Амбиция складывается из общей по месяцу и постоянной по магазину. Без второй части план
    # одинаково напряжённый для всех, и тогда его не выполняет вообще никто: на дашборде выходит
    # «0 из 12» — колонка, из которой ничего не следует. Планы ставят люди, и по одним магазинам
    # они систематически мягче, чем по другим.
    по_магазину = rng.normal(1.0, 0.07, SHOPS)
    смещение = по_магазину[actual["магазин_id"].to_numpy() - 1]
    ambition = rng.normal(1.03, 0.06, len(actual)) * смещение
    return pd.DataFrame(
        {
            "месяц": actual["месяц"],
            "магазин_id": actual["магазин_id"],
            "план_выручки": np.round(actual["сумма"].to_numpy() * ambition, 2),
        }
    )


def _marketing(rng: np.random.Generator) -> pd.DataFrame:
    months = _months()
    channels = list(CHANNELS)
    month_column = np.repeat(months, len(channels))
    channel_column = np.tile(channels, len(months))
    share = np.tile([CHANNELS[name][0] for name in channels], len(months))
    cost = np.tile([CHANNELS[name][1] for name in channels], len(months))
    conversion = np.tile([CHANNELS[name][2] for name in channels], len(months))

    visits = np.maximum(rng.normal(VISITS_PER_MONTH * share, VISITS_PER_MONTH * 0.08 * share), 0).astype(int)
    orders = np.maximum(visits * conversion * rng.normal(1, 0.12, visits.size), 0).astype(int)
    return pd.DataFrame(
        {
            "месяц": month_column,
            "канал": channel_column,
            "визитов": visits,
            "заказов": orders,
            "расходы": np.round(visits * cost, 2),
        }
    )


def _stock(
    rng: np.random.Generator,
    shops: pd.DataFrame,
    products: pd.DataFrame,
    receipts: pd.DataFrame,
    lines: pd.DataFrame,
) -> pd.DataFrame:
    """Остатки на первое число каждого месяца — по выборке товаров, как в настоящей выгрузке.

    Запас считается от продаж, а не сам по себе. В первой версии остаток был случайным числом около
    сорока восьми штук независимо от того, продаётся товар или лежит мёртвым грузом. Оборачиваемость
    выходила 0,11 раза в месяц — запас на девять месяцев вперёд, чего в продуктовой рознице не бывает
    и с чем магазин просто не работает: скоропортящееся списали бы раньше.
    """
    months = _months()
    sample = products.sample(n=STOCK_PRODUCTS, random_state=11)["товар_id"].to_numpy()
    shop_ids = shops["магазин_id"].to_numpy()

    продано = lines.merge(receipts[["чек_id", "магазин_id"]], on="чек_id", how="left")
    за_месяц = продано.groupby(["магазин_id", "товар_id"])["количество"].sum() / len(months)

    сетка_магазин = np.repeat(shop_ids, len(sample))
    сетка_товар = np.tile(sample, len(shop_ids))
    средние = за_месяц.reindex(
        pd.MultiIndex.from_arrays([сетка_магазин, сетка_товар]), fill_value=0.0
    ).to_numpy()

    запас = rng.poisson(np.maximum(средние * STOCK_COVER, 0.5), size=(len(months), средние.size))
    return pd.DataFrame(
        {
            "дата": np.repeat(months, len(shop_ids) * len(sample)),
            "магазин_id": np.tile(сетка_магазин, len(months)),
            "товар_id": np.tile(сетка_товар, len(months)),
            "остаток": запас.reshape(-1),
        }
    )


def _support(rng: np.random.Generator, shops: pd.DataFrame) -> pd.DataFrame:
    count = 4_200
    day = rng.integers(0, DAYS, size=count)
    return pd.DataFrame(
        {
            "обращение_id": np.arange(1, count + 1),
            "дата": [START + timedelta(days=int(value)) for value in day],
            "магазин_id": rng.choice(shops["магазин_id"].to_numpy(), size=count),
            "тема": rng.choice(SUPPORT_TOPICS, size=count, p=[0.28, 0.26, 0.18, 0.16, 0.12]),
            "решено_за_часы": np.round(np.clip(rng.gamma(2.0, 9.0, count), 0.5, 240), 1),
        }
    )
