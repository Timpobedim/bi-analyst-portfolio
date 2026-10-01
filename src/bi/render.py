"""Отрисовка дашборда: одна самодостаточная HTML-страница без единой внешней библиотеки.

Почему так, а не `.pbix`: файл Power BI — это архив с двоичным `Report/Layout` на мегабайты.
Его нельзя открыть без Power BI Desktop, нельзя посмотреть в браузере, нельзя увидеть в истории
изменений, что именно поправили. Здесь дашборд — обычный HTML: открывается двойным щелчком, читается
в системе контроля версий, работает без интернета и без шрифтов со стороны.

Графики рисуются своим SVG: это несколько десятков строк на тип, зато страница весит килобайты
и выглядит одинаково везде.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

INK: Final = "#151a21"
ACCENT: Final = "#2f6f4e"
SECOND: Final = "#a8451f"
THIRD: Final = "#3a6ea5"
PALETTE: Final = (ACCENT, SECOND, THIRD, "#7a5ea8", "#b08900", "#3d7d7a")


@dataclass(frozen=True, slots=True)
class Card:
    """Плитка с числом: заголовок, значение и пояснение."""

    title: str
    value: str
    note: str = ""
    tone: str = ""  # «хорошо», «внимание», «плохо»


@dataclass(frozen=True, slots=True)
class Block:
    """Блок дашборда: заголовок, пояснение и содержимое (таблица или график)."""

    title: str
    body: str
    subtitle: str = ""
    note: str = ""


def money(value: float, digits: int = 0) -> str:
    return f"{number(value, digits)} ₽"


def number(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def percent(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}".replace(".", ",") + "%"


def change(value: float, digits: int = 1) -> str:
    return ("+" if value >= 0 else "") + percent(value, digits)


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], *, align: str = "") -> str:
    """Таблица: первые столбцы по левому краю, числовые — по правому."""
    rules = (align + "l" * len(headers))[: len(headers)]
    head = "".join(
        f'<th class="{"right" if rules[index] == "r" else ""}">{html.escape(str(cell))}</th>'
        for index, cell in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"right" if rules[index] == "r" else ""}">{html.escape(str(cell))}</td>'
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def bars(values: Mapping[str, float], *, unit: str = "", height: int = 260, horizontal: bool = False) -> str:
    """Столбики с подписями значений."""
    if not values:
        return "<p class=\"empty\">нет данных</p>"
    top = max(max(values.values()), 0.0001)
    if horizontal:
        rows = []
        for name, value in values.items():
            width = max(value / top * 100, 0.5)
            rows.append(
                '<div class="row">'
                f'<span class="label">{html.escape(name)}</span>'
                f'<span class="track"><span class="fill" style="width:{width:.1f}%"></span></span>'
                f'<span class="value">{_short(value)}{unit}</span>'
                "</div>"
            )
        return f'<div class="hbars">{"".join(rows)}</div>'

    width = 760
    step = width / max(len(values), 1)
    bar_width = max(step * 0.6, 6)
    parts = []
    for index, (name, value) in enumerate(values.items()):
        bar_height = max(value / top * (height - 46), 2)
        x = index * step + (step - bar_width) / 2
        y = height - 30 - bar_height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" fill="{ACCENT}"/>'
            f'<text class="tick" x="{x + bar_width / 2:.1f}" y="{height - 12}" text-anchor="middle">'
            f"{html.escape(_trim(name))}</text>"
            f'<text class="value" x="{x + bar_width / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle">'
            f"{_short(value)}</text>"
        )
    return _svg(width, height, "".join(parts))


def grouped_bars(labels: Sequence[str], series: Mapping[str, Sequence[float]], *, height: int = 280) -> str:
    """Несколько рядов рядом: план и факт, год и год назад."""
    if not labels or not series:
        return '<p class="empty">нет данных</p>'
    width = 760
    top = max(max(values) for values in series.values()) or 1.0
    group = width / max(len(labels), 1)
    bar = group * 0.8 / max(len(series), 1)
    parts = []
    for position, label in enumerate(labels):
        for index, (name, values) in enumerate(series.items()):
            value = values[position] if position < len(values) else 0.0
            bar_height = max(value / top * (height - 50), 1)
            x = position * group + group * 0.1 + index * bar
            y = height - 32 - bar_height
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar - 2:.1f}" height="{bar_height:.1f}" rx="2" '
                f'fill="{PALETTE[index % len(PALETTE)]}"><title>{html.escape(name)}: {_short(value)}</title></rect>'
            )
        parts.append(
            f'<text class="tick" x="{position * group + group / 2:.1f}" y="{height - 12}" text-anchor="middle">'
            f"{html.escape(_trim(label))}</text>"
        )
    return _svg(width, height, "".join(parts)) + _legend(series.keys())


def lines(labels: Sequence[str], series: Mapping[str, Sequence[float]], *, height: int = 280) -> str:
    """Линии по времени с подписями по краям."""
    if not labels or not series:
        return '<p class="empty">нет данных</p>'
    width = 760
    every = [value for values in series.values() for value in values]
    top, low = max(every), min(min(every), 0)
    span = (top - low) or 1.0
    step = width / max(len(labels) - 1, 1)
    parts = []
    for index, (_name, values) in enumerate(series.items()):
        points = " ".join(
            f"{position * step:.1f},{height - 34 - (value - low) / span * (height - 60):.1f}"
            for position, value in enumerate(values)
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{PALETTE[index % len(PALETTE)]}" stroke-width="2.5"/>'
        )
    for position, label in enumerate(labels):
        if len(labels) > 12 and position % 2:
            continue
        parts.append(
            f'<text class="tick" x="{position * step:.1f}" y="{height - 12}" text-anchor="middle">'
            f"{html.escape(_trim(label, 7))}</text>"
        )
    return _svg(width, height, "".join(parts)) + _legend(series.keys())


def stacked(labels: Sequence[str], series: Mapping[str, Sequence[float]], *, height: int = 280) -> str:
    """Столбики с накоплением: структура выручки по категориям."""
    if not labels or not series:
        return '<p class="empty">нет данных</p>'
    width = 760
    totals = [sum(values[position] for values in series.values()) for position in range(len(labels))]
    top = max(totals) or 1.0
    step = width / max(len(labels), 1)
    bar = step * 0.66
    parts = []
    for position, label in enumerate(labels):
        offset = 0.0
        for index, (name, values) in enumerate(series.items()):
            value = values[position] if position < len(values) else 0.0
            bar_height = value / top * (height - 50)
            y = height - 32 - offset - bar_height
            parts.append(
                f'<rect x="{position * step + (step - bar) / 2:.1f}" y="{y:.1f}" width="{bar:.1f}" '
                f'height="{max(bar_height, 0.5):.1f}" fill="{PALETTE[index % len(PALETTE)]}">'
                f"<title>{html.escape(name)}: {_short(value)}</title></rect>"
            )
            offset += bar_height
        parts.append(
            f'<text class="tick" x="{position * step + step / 2:.1f}" y="{height - 12}" text-anchor="middle">'
            f"{html.escape(_trim(label, 7))}</text>"
        )
    return _svg(width, height, "".join(parts)) + _legend(series.keys())


def heatmap(rows: Sequence[str], columns: Sequence[str], values: Sequence[Sequence[float | None]]) -> str:
    """Тепловая карта: когорты и всё, что смотрят матрицей."""
    if not rows or not columns:
        return '<p class="empty">нет данных</p>'
    every = [value for line in values for value in line if value is not None]
    top = max(every) if every else 1.0
    head = "".join(f"<th>{html.escape(str(name))}</th>" for name in columns)
    body = []
    for index, name in enumerate(rows):
        cells = []
        for position in range(len(columns)):
            value = values[index][position] if position < len(values[index]) else None
            if value is None:
                cells.append('<td class="empty-cell"></td>')
                continue
            weight = min(max(value / top, 0.0), 1.0)
            cells.append(
                f'<td class="heat" style="background: color-mix(in srgb, {ACCENT} {weight * 78:.0f}%, transparent)">'
                f"{percent(value)}</td>"
            )
        body.append(f"<tr><th>{html.escape(str(name))}</th>{''.join(cells)}</tr>")
    return f'<table class="heatmap"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def funnel(steps: Sequence[str], values: Sequence[float]) -> str:
    """Воронка: доля от первого шага и от предыдущего."""
    if not steps or not values:
        return '<p class="empty">нет данных</p>'
    top = values[0] or 1.0
    rows = []
    for index, (step, value) in enumerate(zip(steps, values, strict=False)):
        previous = values[index - 1] if index else value
        rows.append(
            '<div class="row">'
            f'<span class="label">{html.escape(step)}</span>'
            f'<span class="track"><span class="fill" style="width:{value / top * 100:.1f}%"></span></span>'
            f'<span class="value">{_short(value)} · {percent(value / top)}'
            + (f" · от прошлого {percent(value / previous)}" if index else "")
            + "</span></div>"
        )
    return f'<div class="hbars">{"".join(rows)}</div>'


def page(
    *,
    title: str,
    question: str,
    cards: Sequence[Card],
    blocks: Sequence[Block],
    source: str,
    prepared_on: date,
    metrics_note: str = "",
) -> str:
    """Собирает страницу целиком."""
    cards_html = "".join(
        f'<div class="card {_tone(card.tone)}"><div class="card-title">{html.escape(card.title)}</div>'
        f'<div class="card-value">{html.escape(card.value)}</div>'
        + (f'<div class="card-note">{html.escape(card.note)}</div>' if card.note else "")
        + "</div>"
        for card in cards
    )
    blocks_html = "".join(
        f'<section class="block"><h2>{html.escape(block.title)}</h2>'
        + (f'<p class="sub">{html.escape(block.subtitle)}</p>' if block.subtitle else "")
        + f'<div class="body">{block.body}</div>'
        + (f'<p class="note">{html.escape(block.note)}</p>' if block.note else "")
        + "</section>"
        for block in blocks
    )
    note = f'<p class="sub">{html.escape(metrics_note)}</p>' if metrics_note else ""
    return (
        '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n<main>\n"
        f"<h1>{html.escape(title)}</h1>\n"
        f'<p class="question">{html.escape(question)}</p>\n{note}'
        f'<div class="cards">{cards_html}</div>\n{blocks_html}\n'
        f'<footer>Источник: {html.escape(source)}. Собрано {prepared_on:%d.%m.%Y} командой '
        "<code>bi dashboard</code>; витрины пересобираются из данных, страница не правится руками.</footer>\n"
        "</main>\n</body>\n</html>\n"
    )


def _svg(width: int, height: int, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" preserveAspectRatio="xMidYMid meet" '
        f'class="chart">{body}</svg>'
    )


def _legend(names: Iterable[str]) -> str:
    parts = "".join(
        f'<span class="legend-item"><i style="background:{PALETTE[index % len(PALETTE)]}"></i>'
        f"{html.escape(str(name))}</span>"
        for index, name in enumerate(names)
    )
    return f'<div class="legend">{parts}</div>'


def _tone(tone: str) -> str:
    return {"хорошо": "good", "внимание": "warn", "плохо": "bad"}.get(tone, "")


def _trim(text: str, limit: int = 10) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short(value: float) -> str:
    """Короткая запись больших чисел: 1,2 млн вместо 1 234 567."""
    if abs(value) >= 1_000_000_000:
        return number(value / 1_000_000_000, 1) + " млрд"
    if abs(value) >= 1_000_000:
        return number(value / 1_000_000, 1) + " млн"
    if abs(value) >= 10_000:
        return number(value / 1_000, 0) + " тыс"
    if abs(value) >= 1:
        return number(value, 0)
    return number(value, 2)


STYLE: Final = """
:root { color-scheme: light dark; --ink:#151a21; --ink-2:#5c6773; --line:#e1e5ea; --bg:#f5f7f8;
        --card:#ffffff; --good:#1f6b3a; --warn:#8a6100; --bad:#b3261e; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#e9edf2; --ink-2:#98a2ad; --line:#2a3138; --bg:#10141a; --card:#181d24;
          --good:#8fd6a8; --warn:#ffcc80; --bad:#ff8a80; }
}
* { box-sizing: border-box; }
body { margin:0; padding:28px 16px 56px; background:var(--bg); color:var(--ink);
       font:15px/1.55 "Segoe UI", Roboto, Arial, sans-serif; }
main { max-width: 1040px; margin:0 auto; }
h1 { font-size:1.6rem; margin:0 0 6px; }
h2 { font-size:1.05rem; margin:0 0 4px; }
.question { color:var(--ink-2); margin:0 0 18px; }
.sub { color:var(--ink-2); font-size:.9rem; margin:0 0 10px; }
.note { color:var(--ink-2); font-size:.86rem; margin:10px 0 0; }
.cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(190px,1fr)); gap:12px; margin-bottom:22px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.card-title { font-size:.82rem; color:var(--ink-2); }
.card-value { font-size:1.55rem; font-variant-numeric:tabular-nums; margin:4px 0 2px; }
.card-note { font-size:.82rem; color:var(--ink-2); }
.card.good .card-value { color:var(--good); }
.card.warn .card-value { color:var(--warn); }
.card.bad .card-value { color:var(--bad); }
.block { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
.body { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:.9rem; }
th, td { padding:7px 10px; border-bottom:1px solid var(--line); text-align:left; }
th.right, td.right { text-align:right; font-variant-numeric:tabular-nums; }
thead th { color:var(--ink-2); font-weight:600; font-size:.82rem; }
.chart { width:100%; height:auto; }
.chart .tick { font-size:11px; fill:var(--ink-2); }
.chart .value { font-size:11px; fill:var(--ink-2); font-variant-numeric:tabular-nums; }
.legend { display:flex; flex-wrap:wrap; gap:14px; margin-top:8px; font-size:.84rem; color:var(--ink-2); }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }
.hbars .row { display:grid; grid-template-columns:minmax(120px,1fr) 3fr minmax(120px,auto); gap:10px;
              align-items:center; padding:5px 0; }
.hbars .label { font-size:.9rem; }
.hbars .track { background:var(--line); border-radius:6px; height:14px; }
.hbars .fill { display:block; height:14px; border-radius:6px; background:#2f6f4e; }
.hbars .value { font-size:.86rem; color:var(--ink-2); font-variant-numeric:tabular-nums; text-align:right; }
.heatmap td.heat { text-align:right; font-variant-numeric:tabular-nums; }
.heatmap td.empty-cell { background:transparent; }
.empty { color:var(--ink-2); }
footer { color:var(--ink-2); font-size:.84rem; margin-top:24px; }
code { background:var(--line); padding:1px 5px; border-radius:4px; }
@media (max-width:560px) { .hbars .row { grid-template-columns:1fr; } .hbars .value { text-align:left; } }
"""
