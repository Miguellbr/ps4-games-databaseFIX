#!/usr/bin/env python3
"""
Converte catalog.json para um formato normalizado, pensado para uma futura
API/app (Android/PS4).

Uso:
    python scripts/convert_catalog.py
    python scripts/convert_catalog.py --input catalog.json --output src/data/catalog_api.json
    python scripts/convert_catalog.py --pretty

Este script só transforma a estrutura do catálogo. Ele não acessa DLPS,
não resolve encurtadores e não tenta contornar CAPTCHA/anti-bot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


def as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_game(item: Any, fallback_url: str | None = None) -> dict | None:
    if not isinstance(item, dict):
        return None

    title = (
        clean_string(item.get("title"))
        or clean_string(item.get("name"))
        or clean_string(item.get("game_name"))
        or "Unknown"
    )

    title_id = (
        clean_string(item.get("title_id"))
        or clean_string(item.get("titleId"))
        or clean_string(item.get("id"))
    )

    downloads: dict[str, list[str]] = {}
    raw_downloads = item.get("download_links") or {}

    if isinstance(raw_downloads, dict):
        for provider in ("mediafire", "1file", "other", "pkg"):
            urls = []
            for url in as_list(raw_downloads.get(provider)):
                url = clean_string(url)
                if url:
                    urls.append(url)
            if urls:
                downloads[provider] = urls

    if fallback_url and not downloads:
        downloads["pkg"] = [fallback_url]

    game_id = title_id or hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]

    source = {}
    dlps_url = clean_string(item.get("dlps_url"))
    if dlps_url:
        source["dlps_url"] = dlps_url

    return {
        "id": game_id,
        "title": title,
        "title_id": title_id,
        "region": clean_string(item.get("region")),
        "cover": clean_string(item.get("cover")),
        "source": source,
        "downloads": downloads,
        "updates": item.get("updates") if isinstance(item.get("updates"), list) else [],
        "dlcs": item.get("dlcs") if isinstance(item.get("dlcs"), list) else [],
    }


def load_games(data: Any) -> list[dict]:
    games: list[dict] = []

    if isinstance(data, dict) and isinstance(data.get("games"), list):
        source = data["games"]
        for item in source:
            game = normalize_game(item)
            if game:
                games.append(game)

    elif isinstance(data, dict) and isinstance(data.get("DATA"), dict):
        for fallback_url, item in data["DATA"].items():
            game = normalize_game(item, str(fallback_url))
            if game:
                games.append(game)

    elif isinstance(data, list):
        for item in data:
            game = normalize_game(item)
            if game:
                games.append(game)

    else:
        raise ValueError(
            'Formato não reconhecido. Esperado {"games": [...]}, '
            '{"DATA": {...}} ou uma lista.'
        )

    return games


def deduplicate_games(games: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    unique: list[dict] = []
    duplicates = 0

    for game in games:
        key = str(game.get("title_id") or game["id"]).upper()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(game)

    return unique, duplicates


def build_output(games: list[dict], duplicates: int, source: Path) -> dict:
    regions: dict[str, int] = {}
    with_downloads = 0
    with_updates = 0
    with_dlcs = 0

    for game in games:
        region = game.get("region") or "UNKNOWN"
        regions[region] = regions.get(region, 0) + 1
        if game.get("downloads"):
            with_downloads += 1
        if game.get("updates"):
            with_updates += 1
        if game.get("dlcs"):
            with_dlcs += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source.name,
        "metadata": {
            "total_games": len(games),
            "duplicates_removed": duplicates,
            "games_with_downloads": with_downloads,
            "games_with_updates": with_updates,
            "games_with_dlcs": with_dlcs,
            "regions": regions,
        },
        "games": games,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Converte o catálogo PS4 para o formato da API/app."
    )
    parser.add_argument("--input", default="catalog.json")
    parser.add_argument("--output", default="src/data/catalog_api.json")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Gera JSON indentado; por padrão gera JSON compacto.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Arquivo de entrada não encontrado: {input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    games = load_games(data)
    games, duplicates = deduplicate_games(games)
    output = build_output(games, duplicates, input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        if args.pretty:
            json.dump(output, file, ensure_ascii=False, indent=2)
            file.write("\n")
        else:
            json.dump(output, file, ensure_ascii=False, separators=(",", ":"))

    meta = output["metadata"]
    print(f"✓ Catálogo convertido: {output_path}")
    print(f"  Jogos: {meta['total_games']}")
    print(f"  Duplicados removidos: {meta['duplicates_removed']}")
    print(f"  Com downloads: {meta['games_with_downloads']}")
    print(f"  Com updates: {meta['games_with_updates']}")
    print(f"  Com DLCs: {meta['games_with_dlcs']}")
    print(f"  Regiões: {meta['regions']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
