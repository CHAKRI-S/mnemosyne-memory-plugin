"""Deterministic CLI/debug entrypoint for the local Mnemosyne store."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

from . import DEFAULT_MNEMOSYNE_CONFIG, MnemosyneMemoryService, MnemosyneSQLiteStore, _compact_memory


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _parse_metadata(value: str) -> Dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("metadata must be a JSON object")
    return parsed


def _parse_filter(values: list[str]) -> Dict[str, str]:
    filters: Dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError("filters must be key=value")
        key, value = item.split("=", 1)
        filters[key] = value
    return filters


def _default_storage_path() -> Path:
    hermes_home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return Path(str(DEFAULT_MNEMOSYNE_CONFIG.get("storage_path") or hermes_home / "mnemosyne").replace("$HERMES_HOME", str(hermes_home)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-mnemosyne", description="Inspect and manage local Mnemosyne memories")
    parser.add_argument("--storage-path", default=str(_default_storage_path()), help="Mnemosyne storage directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("stats")

    remember = sub.add_parser("remember")
    remember.add_argument("text")
    remember.add_argument("--type", default="fact")
    remember.add_argument("--sensitivity", default="normal")
    remember.add_argument("--metadata", type=_parse_metadata, default={})

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--filter", action="append", default=[])

    inspect = sub.add_parser("inspect")
    inspect.add_argument("id")

    forget = sub.add_parser("forget")
    forget.add_argument("id")

    forget_query = sub.add_parser("forget-query")
    forget_query.add_argument("query")
    forget_query.add_argument("--filter", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = MnemosyneSQLiteStore(args.storage_path)
    service = MnemosyneMemoryService(store)

    try:
        if args.command in {"status", "stats"}:
            payload = {
                "success": True,
                "provider": "mnemosyne",
                "write_policy": "single",
                "storage_path": str(store.storage_path),
                "db_path": str(store.db_path),
                "counts": store.stats(),
            }
        elif args.command == "remember":
            memory_id = service.remember(text=args.text, type=args.type, sensitivity=args.sensitivity, metadata=args.metadata)
            payload = {"success": True, "id": memory_id, "type": args.type, "sensitivity": args.sensitivity}
        elif args.command == "search":
            items = service.search(args.query, filters=_parse_filter(args.filter), limit=max(1, min(args.limit, 50)))
            payload = {"success": True, "count": len(items), "items": [_compact_memory(item, include_metadata=True) for item in items]}
        elif args.command == "inspect":
            payload = service.inspect(args.id)
        elif args.command == "forget":
            payload = service.forget(id=args.id)
        elif args.command == "forget-query":
            payload = service.forget(query=args.query, filters=_parse_filter(args.filter))
        else:
            parser.error("unknown command")
            return 2
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(_json({"success": False, "error": str(exc)}))
        return 1

    print(_json(payload))
    return 0 if payload.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
