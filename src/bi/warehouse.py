"""Склад: поднять базу, загрузить таблицы, собрать витрины и проверить их.

Всё хозяйство — один файл DuckDB. Витрины пересобираются целиком: `bi build` создаёт их заново из
исходных таблиц, поэтому «случайно поправленная руками витрина» здесь невозможна в принципе.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from bi import data, models
from bi.models import BuildResult, CheckResult, Layer

DEFAULT_PATH = "склад.duckdb"


class WarehouseError(RuntimeError):
    """База недоступна или запрос не выполнился."""


@dataclass(frozen=True, slots=True)
class BuildReport:
    """Что получилось при сборке: исходные таблицы, витрины и время."""

    tables: dict[str, int]
    models: tuple[BuildResult, ...]
    seconds: float

    @property
    def line(self) -> str:
        return (
            f"Загружено таблиц: {len(self.tables)} ({sum(self.tables.values())} строк), "
            f"собрано витрин: {len(self.models)}, за {self.seconds:.1f} с"
        )


class Store:
    """Обёртка над DuckDB: загрузка, сборка витрин, проверки и запросы для дашбордов."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = Path(path) if str(path) != ":memory:" else None
        try:
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = duckdb.connect(str(path))
        except (OSError, duckdb.Error) as exc:
            raise WarehouseError(f"Не удалось открыть склад {path}: {exc}") from exc
        self.layer: Layer = models.layer()

    # ── сборка ──────────────────────────────────────────────────────────────────────────────────

    def load(self, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
        """Кладёт исходные таблицы в базу как есть — это «сырой слой»."""
        sizes: dict[str, int] = {}
        for name, frame in tables.items():
            try:
                self.connection.register(f"входные_{name}", frame)
                self.connection.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM входные_{name}")  # noqa: S608
                self.connection.unregister(f"входные_{name}")
            except duckdb.Error as exc:
                raise WarehouseError(f"Не удалось загрузить таблицу «{name}»: {exc}") from exc
            sizes[name] = len(frame)
        return sizes

    def build(self, seed: int = data.SEED) -> BuildReport:
        """Полный цикл: сгенерировать данные, загрузить их и пересобрать витрины."""
        started = time.monotonic()
        warehouse = data.build(seed)
        sizes = self.load(warehouse.tables())
        try:
            built = self.layer.build(self.connection)
        except duckdb.Error as exc:
            raise WarehouseError(f"Витрина не собралась: {exc}") from exc
        return BuildReport(tables=sizes, models=tuple(built), seconds=time.monotonic() - started)

    def check(self) -> list[CheckResult]:
        try:
            return self.layer.check(self.connection)
        except duckdb.Error as exc:
            raise WarehouseError(f"Проверка не выполнилась: {exc}") from exc

    # ── запросы ─────────────────────────────────────────────────────────────────────────────────

    def query(self, sql: str, parameters: Sequence[Any] = ()) -> pd.DataFrame:
        """Запрос к складу — дашборды получают данные только так."""
        try:
            return self.connection.execute(sql, list(parameters)).fetchdf()
        except duckdb.Error as exc:
            raise WarehouseError(f"Запрос не выполнился: {exc}") from exc

    def value(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        frame = self.query(sql, parameters)
        if frame.empty:
            raise WarehouseError("Запрос не вернул ни одной строки")
        return frame.iloc[0, 0]

    def has(self, table: str) -> bool:
        rows = self.connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()
        return bool(rows and rows[0])

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def opened(path: Path | str = DEFAULT_PATH, *, seed: int = data.SEED, rebuild: bool = False) -> Store:
    """Открывает склад и при необходимости собирает его с нуля."""
    store = Store(path)
    if rebuild or not store.has("продажи_месяц"):
        store.build(seed)
    return store
