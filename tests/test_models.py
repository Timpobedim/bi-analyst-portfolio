"""Проверки слоя моделей: порядок сборки, зависимости и сами проверки витрин."""

from __future__ import annotations

import duckdb
import pytest

from bi import models
from bi.models import Check, Layer, Model, ModelError


@pytest.fixture
def соединение() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def слой(*модели: Model) -> Layer:
    return Layer(models=модели)


def проба(**поля: object) -> Model:
    основа: dict[str, object] = {
        "name": "проба",
        "description": "тестовая витрина",
        "sql": "SELECT * FROM (VALUES (5), (7)) AS т(значение)",
    }
    основа.update(поля)
    return Model(**основа)  # type: ignore[arg-type]


# ── порядок и зависимости ───────────────────────────────────────────────────────────────────────


def test_порядок_ставит_зависимости_первыми() -> None:
    слои = слой(
        Model(name="второй", description="", sql="SELECT 1", depends_on=("первый",)),
        Model(name="первый", description="", sql="SELECT 1"),
    )
    assert [модель.name for модель in слои.order()] == ["первый", "второй"]


def test_кольцо_в_зависимостях_не_проходит() -> None:
    слои = слой(
        Model(name="а", description="", sql="SELECT 1", depends_on=("б",)),
        Model(name="б", description="", sql="SELECT 1", depends_on=("а",)),
    )
    with pytest.raises(ModelError, match="кольцо"):
        слои.order()


def test_зависимость_от_несуществующей_модели_не_проходит() -> None:
    слои = слой(Model(name="а", description="", sql="SELECT 1", depends_on=("нет такой",)))
    with pytest.raises(ModelError, match="несуществующих"):
        слои.order()


def test_сборка_возвращает_число_строк(соединение: duckdb.DuckDBPyConnection) -> None:
    результат = слой(проба()).build(соединение)
    assert len(результат) == 1
    assert результат[0].rows == 2
    assert результат[0].seconds >= 0


# ── проверки витрин ─────────────────────────────────────────────────────────────────────────────


def прогнать(соединение: duckdb.DuckDBPyConnection, модель: Model) -> list[models.CheckResult]:
    слои = слой(модель)
    слои.build(соединение)
    return слои.check(соединение)


def test_граница_только_снизу_собирает_корректный_sql(соединение: duckdb.DuckDBPyConnection) -> None:
    """Регрессия: отсутствующая граница подставлялась как float('inf'), и DuckDB не понимал «inf»."""
    модель = проба(
        sql="SELECT * FROM (VALUES (5), (-1)) AS т(значение)",
        checks=(Check("пределы", column="значение", low=0.0),),
    )
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "вне пределов 1"


def test_граница_только_сверху_собирает_корректный_sql(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(
        sql="SELECT * FROM (VALUES (5), (500)) AS т(значение)",
        checks=(Check("пределы", column="значение", high=100.0),),
    )
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "вне пределов 1"


def test_обе_границы_вместе(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(
        sql="SELECT * FROM (VALUES (-3), (5), (500)) AS т(значение)",
        checks=(Check("пределы", column="значение", low=0.0, high=100.0),),
    )
    результат = прогнать(соединение, модель)
    assert результат[0].detail == "вне пределов 2"


def test_значения_внутри_границ_проходят(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(checks=(Check("пределы", column="значение", low=0.0, high=100.0),))
    результат = прогнать(соединение, модель)
    assert результат[0].ok
    assert результат[0].detail == "всё в пределах"


def test_проверка_без_границ_не_падает(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(checks=(Check("пределы", column="значение"),))
    результат = прогнать(соединение, модель)
    assert результат[0].ok
    assert результат[0].detail == "границы не заданы"


def test_пустая_витрина_не_проходит_проверку(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(sql="SELECT 1 AS значение WHERE false", checks=(Check("не пусто"),))
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "строк 0"


def test_непустая_витрина_проходит(соединение: duckdb.DuckDBPyConnection) -> None:
    результат = прогнать(соединение, проба(checks=(Check("не пусто"),)))
    assert результат[0].ok


def test_повторы_в_ключе_ловятся(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(
        sql="SELECT * FROM (VALUES (1), (1), (2)) AS т(значение)",
        checks=(Check("уникальный ключ", column="значение"),),
    )
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "повторов 1"


def test_уникальный_ключ_проходит(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(checks=(Check("уникальный ключ", column="значение"),))
    assert прогнать(соединение, модель)[0].ok


def test_пропуски_ловятся(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(
        sql="SELECT * FROM (VALUES (1), (NULL)) AS т(значение)",
        checks=(Check("без пропусков", column="значение"),),
    )
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "пропусков 1"


def test_битые_ссылки_ловятся(соединение: duckdb.DuckDBPyConnection) -> None:
    соединение.execute("CREATE TABLE справочник AS SELECT * FROM (VALUES (1), (2)) AS т(ключ)")
    модель = проба(
        sql="SELECT * FROM (VALUES (1), (99)) AS т(значение)",
        checks=(Check("ссылка", column="значение", reference="справочник.ключ"),),
    )
    результат = прогнать(соединение, модель)
    assert not результат[0].ok
    assert результат[0].detail == "битых 1"


def test_целые_ссылки_проходят(соединение: duckdb.DuckDBPyConnection) -> None:
    соединение.execute("CREATE TABLE справочник AS SELECT * FROM (VALUES (5), (7)) AS т(ключ)")
    модель = проба(checks=(Check("ссылка", column="значение", reference="справочник.ключ"),))
    assert прогнать(соединение, модель)[0].ok


def test_failures_оставляет_только_упавшие(соединение: duckdb.DuckDBPyConnection) -> None:
    модель = проба(
        sql="SELECT * FROM (VALUES (1), (1)) AS т(значение)",
        checks=(Check("не пусто"), Check("уникальный ключ", column="значение")),
    )
    результат = прогнать(соединение, модель)
    упавшие = models.failures(результат)
    assert len(результат) == 2
    assert len(упавшие) == 1
    assert упавшие[0].title.endswith("ключ уникален")


# ── настоящий слой ──────────────────────────────────────────────────────────────────────────────


def test_настоящий_слой_собирается_в_правильном_порядке() -> None:
    порядок = [модель.name for модель in models.layer().order()]
    for модель in models.MODELS:
        for зависимость in модель.depends_on:
            assert порядок.index(зависимость) < порядок.index(модель.name)


def test_у_каждой_витрины_есть_описание_и_проверки() -> None:
    for модель in models.MODELS:
        assert модель.description.strip()
        assert модель.checks, f"у витрины «{модель.name}» нет ни одной проверки"


def test_имена_витрин_не_повторяются() -> None:
    имена = [модель.name for модель in models.MODELS]
    assert len(имена) == len(set(имена))


def test_строка_результата_читаема(соединение: duckdb.DuckDBPyConnection) -> None:
    сборка = слой(проба()).build(соединение)
    assert "проба" in сборка[0].line
    assert "строк 2" in сборка[0].line
