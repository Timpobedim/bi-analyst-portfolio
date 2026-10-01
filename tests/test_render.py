"""Проверки отрисовки: форматирование чисел, экранирование и устойчивость к пустым данным."""

from __future__ import annotations

from datetime import date

from bi import render
from bi.render import Block, Card

# ── числа ───────────────────────────────────────────────────────────────────────────────────────


def test_числа_с_пробелом_между_разрядами() -> None:
    assert render.number(1_234_567) == "1 234 567"


def test_дробная_часть_через_запятую() -> None:
    assert render.number(0.5, 2) == "0,50"


def test_деньги_со_знаком_рубля() -> None:
    assert render.money(1_500) == "1 500 ₽"


def test_проценты() -> None:
    assert render.percent(0.125) == "12,5%"
    assert render.percent(0.125, 2) == "12,50%"


def test_изменение_показывает_знак() -> None:
    assert render.change(0.05) == "+5,0%"
    assert render.change(-0.05) == "-5,0%"
    assert render.change(0.0) == "+0,0%"


# ── таблица ─────────────────────────────────────────────────────────────────────────────────────


def test_таблица_экранирует_разметку() -> None:
    вывод = render.table(["Товар"], [["<script>alert(1)</script>"]])
    assert "<script>" not in вывод
    assert "&lt;script&gt;" in вывод


def test_выравнивание_по_правому_краю() -> None:
    вывод = render.table(["Имя", "Сумма"], [["а", "1"]], align="lr")
    assert вывод.count('class="right"') == 2  # заголовок и ячейка


def test_таблица_без_строк_остаётся_корректной() -> None:
    вывод = render.table(["Имя"], [])
    assert "<tbody></tbody>" in вывод


# ── графики ─────────────────────────────────────────────────────────────────────────────────────


def test_пустые_данные_не_ломают_графики() -> None:
    for вывод in (
        render.bars({}),
        render.grouped_bars([], {}),
        render.lines([], {}),
        render.stacked([], {}),
        render.heatmap([], [], []),
        render.funnel([], []),
    ):
        assert "нет данных" in вывод


def test_горизонтальные_столбики_рисуют_полосы() -> None:
    вывод = render.bars({"первый": 10.0, "второй": 5.0}, horizontal=True)
    assert вывод.count('class="fill"') == 2
    assert "первый" in вывод


def test_вертикальные_столбики_дают_svg() -> None:
    вывод = render.bars({"а": 1.0, "б": 2.0})
    assert вывод.startswith("<svg")
    assert вывод.count("<rect") == 2


def test_у_нескольких_рядов_есть_легенда() -> None:
    вывод = render.grouped_bars(["янв"], {"план": [1.0], "факт": [2.0]})
    assert "legend" in вывод
    assert "план" in вывод
    assert "факт" in вывод


def test_линии_рисуют_полилинию_на_ряд() -> None:
    вывод = render.lines(["янв", "фев"], {"выручка": [1.0, 2.0], "прибыль": [0.5, 0.7]})
    assert вывод.count("<polyline") == 2


def test_накопление_складывает_ряды() -> None:
    вывод = render.stacked(["янв"], {"а": [1.0], "б": [2.0]})
    assert вывод.count("<rect") == 2


def test_тепловая_карта_отличает_пусто_от_нуля() -> None:
    вывод = render.heatmap(["когорта"], ["0", "1"], [[1.0, None]])
    assert "empty-cell" in вывод
    assert "100,0%" in вывод


def test_воронка_считает_долю_от_первого_и_прошлого_шага() -> None:
    вывод = render.funnel(["визиты", "заказы"], [100.0, 25.0])
    assert "25,0%" in вывод
    assert "от прошлого" in вывод


def test_график_экранирует_подписи() -> None:
    вывод = render.bars({"<b>жирный</b>": 1.0}, horizontal=True)
    assert "<b>" not in вывод
    assert "&lt;b&gt;жирный" in вывод


# ── страница ────────────────────────────────────────────────────────────────────────────────────


def страница() -> str:
    return render.page(
        title="Проба",
        question="Работает ли это?",
        cards=[Card("Число", "42", "пояснение", tone="хорошо")],
        blocks=[Block(title="Блок", body="<p>тело</p>", subtitle="подпись", note="сноска")],
        source="витрина проба",
        prepared_on=date(2026, 9, 13),
        metrics_note="определения метрик",
    )


def test_страница_самодостаточна() -> None:
    вывод = страница()
    assert вывод.startswith("<!doctype html>")
    assert "<style>" in вывод
    assert "http://" not in вывод
    assert "https://" not in вывод


def test_страница_показывает_всё_переданное() -> None:
    вывод = страница()
    for кусок in ("Проба", "Работает ли это?", "42", "пояснение", "Блок", "подпись", "сноска", "витрина проба"):
        assert кусок in вывод, f"на странице нет «{кусок}»"


def test_дата_сборки_в_русском_формате() -> None:
    assert "13.09.2026" in страница()


def test_тон_карточки_превращается_в_класс() -> None:
    assert 'class="card good"' in страница()


def test_страница_работает_в_тёмной_теме() -> None:
    assert "prefers-color-scheme: dark" in страница()
