"""Командная строка: build, test, metrics, list, dashboard, all."""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from bi import metrics as metrics_module
from bi import models
from bi.warehouse import DEFAULT_PATH, Store, WarehouseError, opened

OUT = "дашборды"


def main(argv: Sequence[str] | None = None) -> int:
    _utf8_console()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (WarehouseError, models.ModelError, KeyError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


def _utf8_console() -> None:
    """В стандартной консоли Windows нет знака рубля: переключаем вывод на UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() not in {"utf-8", "utf8"}:
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bi", description="Витрины и дашборды розничной сети")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="собрать склад и витрины заново")
    _common(build)
    build.add_argument("--seed", type=int, default=42)
    build.set_defaults(handler=_build)

    test = commands.add_parser("test", help="проверить витрины")
    _common(test)
    test.set_defaults(handler=_test)

    catalog = commands.add_parser("metrics", help="словарь метрик")
    catalog.set_defaults(handler=_metrics)

    listing = commands.add_parser("list", help="список дашбордов")
    listing.set_defaults(handler=_list)

    single = commands.add_parser("dashboard", help="собрать один дашборд")
    _common(single)
    single.add_argument("name")
    single.add_argument("--out", type=Path, default=Path(OUT))
    single.set_defaults(handler=_dashboard)

    every = commands.add_parser("all", help="собрать все дашборды")
    _common(every)
    every.add_argument("--out", type=Path, default=Path(OUT))
    every.set_defaults(handler=_all)
    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--warehouse", type=Path, default=Path(DEFAULT_PATH))


def _build(args: argparse.Namespace) -> int:
    with Store(args.warehouse) as store:
        report = store.build(args.seed)
        print(report.line)
        for result in report.models:
            print(f"  {result.line}")
    return 0


def _test(args: argparse.Namespace) -> int:
    with opened(args.warehouse) as store:
        results = store.check()
    for result in results:
        print(result.line)
    bad = models.failures(results)
    print(f"\nПроверок {len(results)}, не прошло {len(bad)}.")
    return 1 if bad else 0


def _metrics(_: argparse.Namespace) -> int:
    headers, rows = metrics_module.table()
    widths = [max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(len(headers))]
    print("  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    for row in rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))
    return 0


def _list(_: argparse.Namespace) -> int:
    from bi.dashboards import registry

    for dashboard in registry():
        print(f"{dashboard.name:18s} {dashboard.title}")
        print(f"{'':18s} {dashboard.question}")
    return 0


def _dashboard(args: argparse.Namespace) -> int:
    from bi.dashboards import find

    dashboard = find(args.name)
    if dashboard is None:
        from bi.dashboards import registry

        known = ", ".join(item.name for item in registry())
        raise ValueError(f"Дашборда «{args.name}» нет. Есть: {known}")
    with opened(args.warehouse) as store:
        path = dashboard.build(store, Path(args.out))
    print(f"+ {dashboard.name:18s} {path}")
    return 0


def _all(args: argparse.Namespace) -> int:
    from bi.dashboards import registry

    with opened(args.warehouse) as store:
        for dashboard in registry():
            path = dashboard.build(store, Path(args.out))
            print(f"+ {dashboard.name:18s} {path}")
    print(f"\nГотово: {len(registry())} дашбордов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
