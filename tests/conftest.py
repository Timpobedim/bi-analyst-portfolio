"""Общий склад для тестов: собирается один раз на весь прогон, а не под каждый тест."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bi.warehouse import Store


@pytest.fixture(scope="session")
def склад(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Store]:
    путь = tmp_path_factory.mktemp("склад") / "склад.duckdb"
    хранилище = Store(путь)
    хранилище.build()
    yield хранилище
    хранилище.close()
