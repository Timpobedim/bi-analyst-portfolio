"""Слой моделей: витрины на SQL с зависимостями и проверками — то же, что делает dbt, но в сто строк.

SQL-модели версионируются, собираются в правильном порядке и проверяются тестами. Облако,
планировщик и сам dbt не нужны: ради десятка витрин на одной машине они избыточны.

Каждая модель знает, от чего зависит, и несёт с собой проверки: не пусто, ключ уникален, нет
пропусков в важных полях, ссылки ведут в существующие строки, значения в разумных пределах.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

import duckdb


class ModelError(ValueError):
    """Слой моделей описан неверно: кольцо в зависимостях или ссылка на несуществующую модель."""


@dataclass(frozen=True, slots=True)
class Check:
    """Проверка модели: вид, поле и при необходимости ссылка или границы."""

    kind: str
    column: str = ""
    reference: str = ""
    low: float | None = None
    high: float | None = None

    def title(self, model: str) -> str:
        if self.kind == "не пусто":
            return f"{model}: таблица не пуста"
        if self.kind == "уникальный ключ":
            return f"{model}.{self.column}: ключ уникален"
        if self.kind == "без пропусков":
            return f"{model}.{self.column}: нет пропусков"
        if self.kind == "ссылка":
            return f"{model}.{self.column} → {self.reference}"
        # Границу можно задать с одной стороны, и тогда писать «0.0…None» нельзя: это читают люди.
        if self.low is not None and self.high is not None:
            пределы = f"в пределах {self.low}…{self.high}"
        elif self.low is not None:
            пределы = f"не меньше {self.low}"
        elif self.high is not None:
            пределы = f"не больше {self.high}"
        else:
            пределы = "без заданных границ"
        return f"{model}.{self.column}: значения {пределы}"


@dataclass(frozen=True, slots=True)
class Model:
    """Витрина: имя, SQL, зависимости и проверки."""

    name: str
    description: str
    sql: str
    depends_on: tuple[str, ...] = ()
    checks: tuple[Check, ...] = ()


@dataclass(frozen=True, slots=True)
class BuildResult:
    model: str
    rows: int
    seconds: float

    @property
    def line(self) -> str:
        return f"{self.model}: строк {self.rows}, {self.seconds:.2f} с"


@dataclass(frozen=True, slots=True)
class CheckResult:
    model: str
    title: str
    ok: bool
    detail: str

    @property
    def line(self) -> str:
        return f"{'+' if self.ok else '!'} {self.title}: {self.detail}"


@dataclass
class Layer:
    """Набор моделей, который умеет собираться и проверяться целиком."""

    models: tuple[Model, ...]
    built: list[BuildResult] = field(default_factory=list)

    def order(self) -> tuple[Model, ...]:
        """Топологический порядок: сначала то, от чего зависят остальные."""
        known = {model.name for model in self.models}
        for model in self.models:
            unknown = set(model.depends_on) - known
            if unknown:
                raise ModelError(f"Модель «{model.name}» зависит от несуществующих: {', '.join(sorted(unknown))}")
        ordered: list[Model] = []
        placed: set[str] = set()
        left = list(self.models)
        while left:
            ready = [model for model in left if set(model.depends_on) <= placed]
            if not ready:
                stuck = ", ".join(sorted(model.name for model in left))
                raise ModelError(f"В зависимостях моделей кольцо: {stuck}")
            for model in ready:
                ordered.append(model)
                placed.add(model.name)
            left = [model for model in left if model.name not in placed]
        return tuple(ordered)

    def build(self, connection: duckdb.DuckDBPyConnection) -> list[BuildResult]:
        """Создаёт витрины по порядку зависимостей."""
        results: list[BuildResult] = []
        for model in self.order():
            started = time.monotonic()
            connection.execute(f"CREATE OR REPLACE TABLE {model.name} AS {model.sql}")
            rows = _count(connection, f"SELECT count(*) FROM {model.name}")  # noqa: S608
            results.append(BuildResult(model=model.name, rows=rows, seconds=time.monotonic() - started))
        self.built = results
        return results

    def check(self, connection: duckdb.DuckDBPyConnection) -> list[CheckResult]:
        """Прогоняет все проверки всех моделей."""
        results: list[CheckResult] = []
        for model in self.models:
            for item in model.checks:
                results.append(_run_check(connection, model, item))
        return results


def failures(results: Sequence[CheckResult]) -> list[CheckResult]:
    return [result for result in results if not result.ok]


def _count(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    """Одно число из запроса. DuckDB возвращает `None`, если строк нет, — и на нём всё падало."""
    row = connection.execute(query).fetchone()
    return int(row[0]) if row else 0


def _run_check(connection: duckdb.DuckDBPyConnection, model: Model, check: Check) -> CheckResult:
    title = check.title(model.name)
    if check.kind == "не пусто":
        rows = _count(connection, f"SELECT count(*) FROM {model.name}")  # noqa: S608
        return CheckResult(model.name, title, rows > 0, f"строк {rows}")
    if check.kind == "уникальный ключ":
        query = (
            f"SELECT count(*) FROM (SELECT {check.column} FROM {model.name} "  # noqa: S608
            f"GROUP BY {check.column} HAVING count(*) > 1)"
        )
        doubles = _count(connection, query)
        return CheckResult(model.name, title, doubles == 0, "повторов нет" if not doubles else f"повторов {doubles}")
    if check.kind == "без пропусков":
        empty = _count(connection, f"SELECT count(*) FROM {model.name} WHERE {check.column} IS NULL")  # noqa: S608
        return CheckResult(model.name, title, empty == 0, "пропусков нет" if not empty else f"пропусков {empty}")
    if check.kind == "ссылка":
        table, _, column = check.reference.partition(".")
        query = (
            f"SELECT count(*) FROM {model.name} m LEFT JOIN {table} r "  # noqa: S608
            f"ON m.{check.column} = r.{column} WHERE r.{column} IS NULL AND m.{check.column} IS NOT NULL"
        )
        broken = _count(connection, query)
        return CheckResult(model.name, title, broken == 0, "все ссылки на месте" if not broken else f"битых {broken}")
    # Границы могут быть заданы с одной стороны: бесконечность в SQL писать нельзя.
    conditions = []
    if check.low is not None:
        conditions.append(f"{check.column} < {check.low}")
    if check.high is not None:
        conditions.append(f"{check.column} > {check.high}")
    if not conditions:
        return CheckResult(model.name, title, True, "границы не заданы")
    query = (
        f"SELECT count(*) FROM {model.name} "  # noqa: S608
        f"WHERE {check.column} IS NOT NULL AND ({' OR '.join(conditions)})"
    )
    outside = _count(connection, query)
    return CheckResult(model.name, title, outside == 0, "всё в пределах" if not outside else f"вне пределов {outside}")


# ── сами витрины ────────────────────────────────────────────────────────────────────────────────

MODELS: Final[tuple[Model, ...]] = (
    Model(
        name="продажи_позиции",
        description="Каждая проданная позиция с датой, магазином, категорией и себестоимостью — основа всего.",
        sql="""
        SELECT ч.чек_id,
               ч.дата,
               date_trunc('month', ч.дата) AS месяц,
               ч.магазин_id,
               ч.клиент_id,
               ч.канал,
               п.товар_id,
               т.категория,
               т.поставщик,
               п.количество,
               п.цена,
               п.скидка,
               п.количество * п.цена AS выручка,
               п.количество * т.себестоимость AS себестоимость
        FROM позиции п
        JOIN чеки ч USING (чек_id)
        JOIN товары т USING (товар_id)
        """,
        checks=(
            Check("не пусто"),
            Check("без пропусков", column="выручка"),
            Check("ссылка", column="магазин_id", reference="магазины.магазин_id"),
            Check("пределы", column="скидка", low=0.0, high=0.5),
        ),
    ),
    Model(
        name="продажи_день",
        description="Выручка, чеки и прибыль по дням и магазинам.",
        depends_on=("продажи_позиции",),
        sql="""
        SELECT дата,
               месяц,
               магазин_id,
               count(DISTINCT чек_id) AS чеков,
               sum(выручка) AS выручка,
               sum(себестоимость) AS себестоимость,
               sum(выручка) - sum(себестоимость) AS прибыль,
               sum(количество) AS позиций
        FROM продажи_позиции
        GROUP BY 1, 2, 3
        """,
        checks=(Check("не пусто"), Check("пределы", column="выручка", low=0.0)),
    ),
    Model(
        name="продажи_месяц",
        description="Помесячная витрина по магазинам: выручка, прибыль, средний чек и выполнение плана.",
        depends_on=("продажи_день",),
        sql="""
        SELECT д.месяц,
               д.магазин_id,
               м.название AS магазин,
               м.город,
               м.формат,
               sum(д.выручка) AS выручка,
               sum(д.прибыль) AS прибыль,
               sum(д.чеков) AS чеков,
               sum(д.выручка) / nullif(sum(д.чеков), 0) AS средний_чек,
               sum(д.прибыль) / nullif(sum(д.выручка), 0) AS маржинальность,
               max(п.план_выручки) AS план,
               sum(д.выручка) / nullif(max(п.план_выручки), 0) AS выполнение_плана
        FROM продажи_день д
        JOIN магазины м USING (магазин_id)
        LEFT JOIN план п ON п.магазин_id = д.магазин_id AND п.месяц = д.месяц
        GROUP BY 1, 2, 3, 4, 5
        """,
        checks=(
            Check("не пусто"),
            Check("уникальный ключ", column="месяц, магазин_id"),
            Check("пределы", column="маржинальность", low=0.0, high=1.0),
        ),
    ),
    Model(
        name="товар_месяц",
        description="Продажи по товарам и месяцам — основа ABC-анализа и оборачиваемости.",
        depends_on=("продажи_позиции",),
        sql="""
        SELECT месяц,
               товар_id,
               категория,
               sum(выручка) AS выручка,
               sum(себестоимость) AS себестоимость,
               sum(количество) AS штук
        FROM продажи_позиции
        GROUP BY 1, 2, 3
        """,
        checks=(Check("не пусто"), Check("ссылка", column="товар_id", reference="товары.товар_id")),
    ),
    Model(
        name="клиент_итог",
        description="Итог по каждому покупателю: давность, частота и деньги — три числа для RFM.",
        depends_on=("продажи_позиции",),
        sql="""
        WITH граница AS (SELECT max(дата) AS сегодня FROM продажи_позиции)
        SELECT клиент_id,
               max(дата) AS последняя_покупка,
               date_diff('day', max(дата), (SELECT сегодня FROM граница)) AS давность_дней,
               count(DISTINCT чек_id) AS покупок,
               sum(выручка) AS деньги,
               sum(выручка) / count(DISTINCT чек_id) AS средний_чек
        FROM продажи_позиции
        GROUP BY 1
        """,
        checks=(
            Check("не пусто"),
            Check("уникальный ключ", column="клиент_id"),
            Check("пределы", column="покупок", low=1),
        ),
    ),
    Model(
        name="возвраты_месяц",
        description="Возвраты по месяцам, магазинам и причинам — вместе с долей от выручки.",
        depends_on=("продажи_позиции",),
        sql="""
        SELECT п.месяц,
               п.магазин_id,
               в.причина,
               sum(в.количество * п.цена) AS сумма_возвратов,
               count(*) AS случаев
        FROM возвраты в
        JOIN продажи_позиции п ON п.чек_id = в.чек_id AND п.товар_id = в.товар_id
        GROUP BY 1, 2, 3
        """,
        checks=(Check("не пусто"), Check("пределы", column="сумма_возвратов", low=0.0)),
    ),
    Model(
        name="маркетинг_месяц",
        description="Каналы привлечения: визиты, заказы, расходы, стоимость заказа и окупаемость.",
        depends_on=("продажи_месяц",),
        sql="""
        WITH сеть AS (
            SELECT месяц, sum(выручка) AS выручка_сети, sum(чеков) AS чеков_сети
            FROM продажи_месяц GROUP BY 1
        )
        SELECT м.месяц,
               м.канал,
               м.визитов,
               м.заказов,
               м.расходы,
               м.расходы / nullif(м.заказов, 0) AS стоимость_заказа,
               с.выручка_сети
                   * (м.заказов * 1.0 / nullif(sum(м.заказов) OVER (PARTITION BY м.месяц), 0)) AS выручка_канала
        FROM маркетинг м
        JOIN сеть с ON с.месяц = CAST(м.месяц AS TIMESTAMP)
        """,
        checks=(Check("не пусто"), Check("пределы", column="расходы", low=0.0)),
    ),
    Model(
        name="остатки_месяц",
        description="Остатки и оборачиваемость: сколько запаса лежит и как быстро он обновляется.",
        depends_on=("товар_месяц",),
        sql="""
        SELECT CAST(о.дата AS TIMESTAMP) AS месяц,
               о.магазин_id,
               sum(о.остаток) AS остаток_штук,
               sum(о.остаток * т.себестоимость) AS остаток_рублей
        FROM остатки о
        JOIN товары т USING (товар_id)
        GROUP BY 1, 2
        """,
        checks=(Check("не пусто"), Check("пределы", column="остаток_штук", low=0)),
    ),
    Model(
        name="персонал_месяц",
        description="Численность, увольнения и фонд оплаты труда по магазинам и месяцам.",
        depends_on=("продажи_месяц",),
        sql="""
        WITH месяцы AS (SELECT DISTINCT месяц FROM продажи_месяц)
        SELECT м.месяц,
               с.магазин_id,
               count(*) FILTER (
                   WHERE CAST(с.принят AS TIMESTAMP) <= м.месяц
                     AND (с.уволен IS NULL OR CAST(с.уволен AS TIMESTAMP) > м.месяц)
               ) AS сотрудников,
               count(*) FILTER (WHERE date_trunc('month', CAST(с.уволен AS TIMESTAMP)) = м.месяц) AS уволено,
               sum(с.оклад) FILTER (
                   WHERE CAST(с.принят AS TIMESTAMP) <= м.месяц
                     AND (с.уволен IS NULL OR CAST(с.уволен AS TIMESTAMP) > м.месяц)
               ) AS фот
        FROM месяцы м
        CROSS JOIN сотрудники с
        GROUP BY 1, 2
        """,
        checks=(Check("не пусто"), Check("пределы", column="сотрудников", low=0)),
    ),
    Model(
        name="обращения_месяц",
        description="Обращения покупателей: темы, сроки решения и связь с магазином.",
        depends_on=("продажи_месяц",),
        sql="""
        SELECT date_trunc('month', CAST(дата AS TIMESTAMP)) AS месяц,
               магазин_id,
               тема,
               count(*) AS обращений,
               avg(решено_за_часы) AS среднее_время_часов,
               quantile_cont(решено_за_часы, 0.9) AS девяностый_процентиль
        FROM обращения
        GROUP BY 1, 2, 3
        """,
        checks=(Check("не пусто"), Check("пределы", column="среднее_время_часов", low=0.0, high=240.0)),
    ),
)


def layer() -> Layer:
    return Layer(models=MODELS)
