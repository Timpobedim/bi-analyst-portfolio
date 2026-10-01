"""Проверки склада: загрузка, сборка витрин, запросы и понятные ошибки."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bi import models
from bi.warehouse import Store, WarehouseError, opened


def test_сборка_создаёт_все_витрины(склад: Store) -> None:
    for модель in models.MODELS:
        assert склад.has(модель.name), f"витрины «{модель.name}» нет"


def test_отчёт_о_сборке_читаем(tmp_path: Path) -> None:
    with Store(tmp_path / "склад.duckdb") as хранилище:
        отчёт = хранилище.build()
    assert "Загружено таблиц" in отчёт.line
    assert отчёт.tables
    assert len(отчёт.models) == 10
    assert отчёт.seconds > 0


def test_все_проверки_настоящих_витрин_проходят(склад: Store) -> None:
    результаты = склад.check()
    упавшие = [результат.line for результат in результаты if not результат.ok]
    assert упавшие == []
    assert len(результаты) > 20


def test_запрос_возвращает_таблицу(склад: Store) -> None:
    таблица = склад.query("SELECT count(*) AS всего FROM продажи_месяц")
    assert isinstance(таблица, pd.DataFrame)
    assert int(таблица["всего"].iloc[0]) > 0


def test_запрос_с_параметрами(склад: Store) -> None:
    таблица = склад.query("SELECT * FROM магазины WHERE магазин_id = ?", [1])
    assert len(таблица) == 1


def test_одно_значение(склад: Store) -> None:
    assert int(склад.value("SELECT count(*) FROM магазины")) == 12


def test_пустой_ответ_даёт_понятную_ошибку(склад: Store) -> None:
    with pytest.raises(WarehouseError, match="ни одной строки"):
        склад.value("SELECT 1 WHERE false")


def test_неверный_запрос_даёт_понятную_ошибку(склад: Store) -> None:
    with pytest.raises(WarehouseError, match="не выполнился"):
        склад.query("SELECT нет_такой_колонки FROM магазины")


def test_has_различает_существующие_таблицы(склад: Store) -> None:
    assert склад.has("продажи_месяц")
    assert not склад.has("таблицы_нет")


def test_opened_собирает_склад_если_его_нет(tmp_path: Path) -> None:
    путь = tmp_path / "новый.duckdb"
    with opened(путь) as хранилище:
        assert хранилище.has("продажи_месяц")
    assert путь.exists()


def test_opened_не_пересобирает_готовый_склад(tmp_path: Path) -> None:
    путь = tmp_path / "готовый.duckdb"
    with Store(путь) as хранилище:
        хранилище.build()
        хранилище.connection.execute("CREATE TABLE метка AS SELECT 1 AS значение")
    with opened(путь) as снова:
        assert снова.has("метка"), "склад пересобрали, хотя он уже был готов"


def test_opened_пересобирает_по_требованию(tmp_path: Path) -> None:
    путь = tmp_path / "пересборка.duckdb"
    with Store(путь) as хранилище:
        хранилище.build()
        хранилище.connection.execute("CREATE TABLE метка AS SELECT 1 AS значение")
    with opened(путь, rebuild=True) as снова:
        assert снова.has("продажи_месяц")


def test_разные_зёрна_дают_разные_витрины(tmp_path: Path) -> None:
    выручка = []
    for зерно in (1, 2):
        with Store(tmp_path / f"склад-{зерно}.duckdb") as хранилище:
            хранилище.build(зерно)
            выручка.append(float(хранилище.value("SELECT sum(выручка) FROM продажи_месяц")))
    assert выручка[0] != выручка[1]


def test_склад_в_памяти_работает() -> None:
    with Store(":memory:") as хранилище:
        хранилище.build()
        assert хранилище.has("продажи_месяц")
