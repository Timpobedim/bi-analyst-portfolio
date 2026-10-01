"""Проверки командной строки: коды возврата и то, что команды действительно что-то делают."""

from __future__ import annotations

from pathlib import Path

import pytest

from bi.cli import main


def test_список_дашбордов(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    вывод = capsys.readouterr().out
    assert "sales" in вывод
    assert "data_quality" in вывод
    assert вывод.count("\n") >= 28  # по две строки на дашборд


def test_словарь_метрик(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["metrics"]) == 0
    assert len(capsys.readouterr().out.splitlines()) > 10


def test_сборка_склада(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "--warehouse", str(tmp_path / "склад.duckdb")]) == 0
    assert "Загружено таблиц" in capsys.readouterr().out


def test_проверка_витрин(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    путь = str(tmp_path / "склад.duckdb")
    assert main(["build", "--warehouse", путь]) == 0
    capsys.readouterr()
    assert main(["test", "--warehouse", путь]) == 0
    assert "не прошло 0" in capsys.readouterr().out


def test_один_дашборд(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    путь = str(tmp_path / "склад.duckdb")
    вывод = tmp_path / "дашборды"
    assert main(["dashboard", "sales", "--warehouse", путь, "--out", str(вывод)]) == 0
    assert (вывод / "01-продажи" / "дашборд.html").exists()
    assert "sales" in capsys.readouterr().out


def test_неизвестный_дашборд_даёт_подсказку(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    код = main(["dashboard", "такого-нет", "--warehouse", str(tmp_path / "склад.duckdb")])
    assert код == 2
    assert "Есть:" in capsys.readouterr().err


def test_все_дашборды(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    вывод = tmp_path / "дашборды"
    assert main(["all", "--warehouse", str(tmp_path / "склад.duckdb"), "--out", str(вывод)]) == 0
    страницы = list(вывод.rglob("дашборд.html"))
    assert len(страницы) == 14
    assert "Готово: 14" in capsys.readouterr().out


def test_без_команды_не_запускается() -> None:
    with pytest.raises(SystemExit):
        main([])
