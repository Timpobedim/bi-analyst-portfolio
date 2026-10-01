"""Проверки генератора данных: период, согласованность таблиц и намеренные неидеальности."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from bi import data


@pytest.fixture(scope="module")
def склад() -> data.Warehouse:
    return data.build(data.SEED)


def месяцы(значения: object) -> set[tuple[int, int]]:
    """Множество месяцев в колонке — так таблицы с разным типом даты сравнимы между собой."""
    моменты = pd.to_datetime(pd.Series(list(значения)))  # type: ignore[call-overload]
    return {(момент.year, момент.month) for момент in моменты}


def test_период_начинается_и_кончается_там_где_задано(склад: data.Warehouse) -> None:
    assert склад.чеки["дата"].min() == data.START
    assert склад.чеки["дата"].max() == data.START + timedelta(days=data.DAYS - 1)


def test_в_периоде_ровно_двадцать_четыре_полных_месяца(склад: data.Warehouse) -> None:
    """Двадцать четыре нужны для сравнения года к году; неполный месяц в конце ломал бы графики."""
    assert len(месяцы(склад.чеки["дата"])) == 24
    assert склад.чеки["дата"].max().day == 31


def test_маркетинг_и_остатки_покрывают_те_же_месяцы_что_и_продажи(склад: data.Warehouse) -> None:
    """Регрессия: раньше они брали DAYS // 30 месяцев и теряли последний."""
    продажи = месяцы(склад.чеки["дата"])
    assert месяцы(склад.маркетинг["месяц"]) == продажи
    assert месяцы(склад.остатки["дата"]) == продажи
    assert месяцы(склад.план["месяц"]) == продажи


def test_магазин_не_торгует_до_своего_открытия(склад: data.Warehouse) -> None:
    открытие = dict(zip(склад.магазины["магазин_id"], склад.магазины["открыт"], strict=True))
    for магазин, момент in открытие.items():
        чеки = склад.чеки[склад.чеки["магазин_id"] == магазин]
        assert чеки["дата"].min() >= момент, f"магазин {магазин} торговал до открытия"


def test_поздний_магазин_открылся_внутри_периода(склад: data.Warehouse) -> None:
    строка = склад.магазины[склад.магазины["магазин_id"] == data.LATE_SHOP].iloc[0]
    assert строка["открыт"] == data.LATE_OPENING
    assert data.START < data.LATE_OPENING < data.START + timedelta(days=data.DAYS)


def test_магазин_на_ремонте_не_торговал_весь_месяц(склад: data.Warehouse) -> None:
    чеки = склад.чеки
    свои = чеки[чеки["магазин_id"] == data.REPAIR_SHOP]
    ремонт = [
        момент
        for момент in свои["дата"]
        if момент.year == data.REPAIR_MONTH.year and момент.month == data.REPAIR_MONTH.month
    ]
    assert ремонт == []


def test_остальные_магазины_в_месяц_ремонта_работали(склад: data.Warehouse) -> None:
    чеки = склад.чеки
    чужие = чеки[chuzhie_mask(чеки)]
    assert len(чужие) > 0


def chuzhie_mask(чеки: pd.DataFrame) -> pd.Series:
    даты = pd.to_datetime(pd.Series(list(чеки["дата"])))
    свой_месяц = (даты.dt.year == data.REPAIR_MONTH.year) & (даты.dt.month == data.REPAIR_MONTH.month)
    return свой_месяц.to_numpy() & (чеки["магазин_id"] != data.REPAIR_SHOP).to_numpy()


def test_сотрудник_не_принят_раньше_открытия_магазина(склад: data.Warehouse) -> None:
    открытие = dict(zip(склад.магазины["магазин_id"], склад.магазины["открыт"], strict=True))
    ранние = [
        (сотрудник, магазин)
        for сотрудник, магазин, принят in zip(
            склад.сотрудники["сотрудник_id"],
            склад.сотрудники["магазин_id"],
            склад.сотрудники["принят"],
            strict=True,
        )
        if принят < открытие[магазин]
    ]
    assert ранние == []


def test_уволенные_ушли_не_раньше_чем_пришли(склад: data.Warehouse) -> None:
    сотрудники = склад.сотрудники
    ушедшие = сотрудники[сотрудники["уволен"].notna()]
    assert len(ушедшие) > 0
    assert all(
        уволен > принят
        for принят, уволен in zip(ушедшие["принят"], ушедшие["уволен"], strict=True)
    )


def test_сборка_воспроизводима_по_зерну() -> None:
    первая, вторая = data.build(7), data.build(7)
    assert len(первая.чеки) == len(вторая.чеки)
    assert первая.позиции["цена"].sum() == вторая.позиции["цена"].sum()


def test_разные_зёрна_дают_разные_данные() -> None:
    assert len(data.build(1).чеки) != len(data.build(2).чеки)


def test_у_части_товаров_не_заполнен_поставщик(склад: data.Warehouse) -> None:
    """Пропуски в справочнике заложены намеренно: дашборды обязаны их показывать, а не прятать."""
    пусто = int(склад.товары["поставщик"].isna().sum())
    assert 0 < пусто < len(склад.товары)


def test_цена_всегда_выше_себестоимости(склад: data.Warehouse) -> None:
    товары = склад.товары
    assert bool((товары["цена"] > товары["себестоимость"]).all())


def test_скидки_не_выходят_за_половину_цены(склад: data.Warehouse) -> None:
    assert float(склад.позиции["скидка"].max()) <= 0.5
    assert float(склад.позиции["скидка"].min()) >= 0.0


def test_покупатели_приходят_в_разные_месяцы(склад: data.Warehouse) -> None:
    """Регрессия: при равномерном выборе клиента почти вся база попадала в первую когорту."""
    чеки = склад.чеки.copy()
    чеки["месяц"] = pd.to_datetime(pd.Series(list(чеки["дата"]))).dt.to_period("M").to_numpy()
    первая_покупка = чеки.groupby("клиент_id")["месяц"].min()
    когорты = первая_покупка.value_counts()
    assert len(когорты) >= 20
    assert float(когорты.max() / когорты.sum()) < 0.5


def test_покупатели_со_временем_перестают_ходить(склад: data.Warehouse) -> None:
    чеки = склад.чеки
    последний = data.START + timedelta(days=data.DAYS - 32)
    активные = чеки[чеки["дата"] >= последний]["клиент_id"].nunique()
    всего = чеки["клиент_id"].nunique()
    assert активные < всего


def test_возвраты_ссылаются_на_проданные_позиции(склад: data.Warehouse) -> None:
    проданные = set(zip(склад.позиции["чек_id"], склад.позиции["товар_id"], strict=True))
    возвращённые = set(zip(склад.возвраты["чек_id"], склад.возвраты["товар_id"], strict=True))
    assert возвращённые <= проданные


def test_план_есть_на_каждый_месяц_каждого_работающего_магазина(склад: data.Warehouse) -> None:
    чеки = склад.чеки.copy()
    чеки["месяц"] = pd.to_datetime(pd.Series(list(чеки["дата"]))).dt.to_period("M").to_numpy()
    пары_продаж = set(zip(чеки["месяц"].astype(str), чеки["магазин_id"], strict=True))
    план = склад.план
    месяцы_плана = pd.to_datetime(pd.Series(list(план["месяц"]))).dt.to_period("M").astype(str)
    пары_плана = set(zip(месяцы_плана, план["магазин_id"], strict=True))
    assert пары_продаж <= пары_плана


def test_все_таблицы_непустые(склад: data.Warehouse) -> None:
    for имя, таблица in склад.tables().items():
        assert len(таблица) > 0, f"таблица «{имя}» пуста"
