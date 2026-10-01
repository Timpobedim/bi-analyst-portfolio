"""Проверки словаря метрик: он один на все дашборды и потому обязан быть полным и непротиворечивым."""

from __future__ import annotations

import pytest

from bi import metrics


def test_в_словаре_есть_метрики() -> None:
    assert len(metrics.CATALOG) >= 15


def test_ключи_не_повторяются() -> None:
    ключи = [метрика.key for метрика in metrics.CATALOG]
    assert len(ключи) == len(set(ключи))


def test_названия_не_повторяются() -> None:
    """Два разных определения под одним названием — ровно та беда, ради которой словарь и заведён."""
    названия = [метрика.name for метрика in metrics.CATALOG]
    assert len(названия) == len(set(названия))


def test_у_каждой_метрики_заполнены_обязательные_поля() -> None:
    for метрика in metrics.CATALOG:
        assert метрика.key.strip(), "у метрики нет ключа"
        assert метрика.name.strip(), f"у метрики «{метрика.key}» нет названия"
        assert метрика.formula.strip(), f"у метрики «{метрика.key}» нет формулы"
        assert метрика.definition.strip(), f"у метрики «{метрика.key}» нет определения"
        assert метрика.unit.strip(), f"у метрики «{метрика.key}» нет единицы измерения"


def test_метрика_находится_по_ключу() -> None:
    первая = metrics.CATALOG[0]
    assert metrics.metric(первая.key) is первая


def test_неизвестный_ключ_это_ошибка_а_не_тихий_ноль() -> None:
    with pytest.raises(KeyError, match="нет в словаре"):
        metrics.metric("такой-метрики-нет")


def test_ошибка_подсказывает_известные_ключи() -> None:
    with pytest.raises(KeyError) as ошибка:
        metrics.metric("нет")
    assert metrics.CATALOG[0].key in str(ошибка.value)


def test_таблица_содержит_все_метрики() -> None:
    заголовки, строки = metrics.table()
    assert len(заголовки) == 5
    assert len(строки) == len(metrics.CATALOG)
    assert all(len(строка) == len(заголовки) for строка in строки)


def test_в_таблице_нет_пустых_ячеек() -> None:
    _, строки = metrics.table()
    for строка in строки:
        for ячейка in строка:
            assert ячейка.strip()


def test_строка_метрики_читается() -> None:
    метрика = metrics.CATALOG[0]
    строка = метрика.line()
    assert метрика.name in строка
    assert метрика.unit in строка
    assert метрика.definition in строка


def test_денежные_метрики_в_рублях() -> None:
    выручка = metrics.metric("revenue")
    assert выручка.unit == "₽"
    assert выручка.caveat, "у выручки обязана быть оговорка про возвраты"


def test_доли_измеряются_в_процентах() -> None:
    assert metrics.metric("margin_share").unit == "%"
