"""Проверки дашбордов: реестр в порядке и каждая страница действительно собирается."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bi.dashboards import Dashboard, find, registry
from bi.warehouse import Store

ВСЕ = registry()


def test_в_реестре_четырнадцать_дашбордов() -> None:
    assert len(ВСЕ) == 14


def test_имена_и_папки_не_повторяются() -> None:
    assert len({дашборд.name for дашборд in ВСЕ}) == len(ВСЕ)
    assert len({дашборд.folder for дашборд in ВСЕ}) == len(ВСЕ)


def test_у_каждого_дашборда_есть_вопрос_и_адресат() -> None:
    for дашборд in ВСЕ:
        assert дашборд.question.strip().endswith("?"), f"«{дашборд.name}» не задаёт вопроса"
        assert дашборд.audience.strip(), f"у «{дашборд.name}» не указан адресат"
        assert дашборд.title.strip()


def test_поиск_по_имени() -> None:
    assert find("sales") is not None
    assert find("такого-нет") is None


@pytest.mark.parametrize("дашборд", ВСЕ, ids=[дашборд.name for дашборд in ВСЕ])
def test_дашборд_собирается_в_самодостаточную_страницу(
    дашборд: Dashboard, склад: Store, tmp_path: Path
) -> None:
    путь = дашборд.build(склад, tmp_path)

    assert путь.exists()
    assert путь.parent.name == дашборд.folder
    страница = путь.read_text("utf-8")

    assert страница.startswith("<!doctype html>")
    assert дашборд.title in страница
    assert дашборд.question in страница
    assert "<footer>" in страница
    # Ни одной внешней загрузки: страница обязана открываться без интернета.
    assert "http://" not in страница
    assert "https://" not in страница


@pytest.mark.parametrize("дашборд", ВСЕ, ids=[дашборд.name for дашборд in ВСЕ])
def test_на_странице_нет_невычисленных_чисел(дашборд: Dashboard, склад: Store, tmp_path: Path) -> None:
    """`nan` на дашборде означает, что где-то поделили на ноль и показали это пользователю."""
    страница = дашборд.build(склад, tmp_path).read_text("utf-8")
    assert not re.search(r"\bnan\b", страница, re.IGNORECASE)
    assert "None" not in страница
