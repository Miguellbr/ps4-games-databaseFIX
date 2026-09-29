#!/usr/bin/env python3
"""
Merge a public PS4 download-link catalog into this project's catalog.

The importer does NOT resolve FileCrypt, bypass CAPTCHA/PoW, or execute third-party
JavaScript. It only imports already-published direct host URLs from a local JSON
file or a URL supplied by the user.

Expected source shape (flexible):
{
  "games": [
    {
      "name": "...",
      "title_id": "CUSA...",
      "page_url": "...",
      "download_links": {
        "mediafire": ["https://www.mediafire.com/..."],
        "1file": ["https://1fichier.com/..."],
        "other": ["..."]
      }
    }
  ]
}

Usage:
  python scripts/merge_download_catalog.py \
      --source ps4_games_expanded.json \
      --catalog catalog.json \
      --output catalog_with_downloads.json

Or with a public raw JSON URL:
  python scripts/merge_download_catalog.py \
      --source-url "https://raw.githubusercontent.com/.../ps4_games_expanded.json" \
      --catalog catalog.json \
      --output catalog_with_downloads.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


HOSTS = {
    "mediafire": ("mediafire.com", "www.mediafire.com"),
    "1file": ("1fichier.com", "www.1fichier.com"),
}


def clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_title(value: Any) -> str:
    value = clean(value) or ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def title_id(value: Any) -> str | None:
    value = clean(value)
    if not value:
        return None
    match = re.search(r"\bCUSA\d{5}\b", value, re.I)
    return match.group(0).upper() if match else value


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def host_for(url: str) -> str | None:
    lower = url.lower()
    for host, domains in HOSTS.items():
        if any(domain in lower for domain in domains):
            return host
    return None


def clean_urls(value: Any, provider: str) -> list[str]:
    result = []
    for item in as_list(value):
        url = clean(item)
        if not url or not url.lower().startswith(("http://", "https://")):
            continue
        if host_for(url) == provider and url not in result:
            result.append(url)
    return result


def extract_source_games(data: Any) -> list[dict]:
    if isinstance(data, dict):
        for key in ("games", "data", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    return [x for x in data if isinstance(x, dict)]


def source_downloads(item: dict) -> dict[str, list[str]]:
    raw = item.get("download_links") or item.get("downloads") or {}
    if not isinstance(raw, dict):
        return {}

    result = {}
    for provider in HOSTS:
        urls = clean_urls(raw.get(provider), provider)
        if urls:
            result[provider] = urls
    return result


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_url(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": "ps4-games-databaseFIX-catalog-importer/1.0",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", type=Path, help="local source JSON")
    group.add_argument("--source-url", help="public JSON URL")
    parser.add_argument("--catalog", type=Path, default=Path("catalog.json"))
    parser.add_argument("--output", type=Path, default=Path("catalog_with_downloads.json"))
    args = parser.parse_args()

    try:
        source = load_json_file(args.source) if args.source else load_json_url(args.source_url)
        catalog = load_json_file(args.catalog)
    except Exception as exc:
        print(f"Erro ao carregar dados: {exc}", file=sys.stderr)
        return 1

    games = catalog.get("games") if isinstance(catalog, dict) else None
    if not isinstance(games, list):
        print("catalog.json não possui uma lista 'games'.", file=sys.stderr)
        return 1

    by_id: dict[str, dict] = {}
    by_title: dict[str, dict] = {}

    for game in games:
        if not isinstance(game, dict):
            continue
        tid = title_id(game.get("title_id"))
        title = normalize_title(game.get("title"))
        if tid:
            by_id[tid] = game
        if title:
            by_title[title] = game

    matched = 0
    unmatched = 0
    imported_urls = 0
    mediafire = 0
    onefile = 0

    for item in extract_source_games(source):
        tid = title_id(item.get("title_id") or item.get("titleId") or item.get("id"))
        title = normalize_title(
            item.get("title") or item.get("name") or item.get("game_name")
        )

        target = by_id.get(tid) if tid else None
        if target is None and title:
            target = by_title.get(title)

        if target is None:
            unmatched += 1
            continue

        downloads = source_downloads(item)
        if not downloads:
            continue

        target_downloads = target.setdefault("download_links", {})
        for provider, urls in downloads.items():
            current = target_downloads.setdefault(provider, [])
            for url in urls:
                if url not in current:
                    current.append(url)
                    imported_urls += 1
                    if provider == "mediafire":
                        mediafire += 1
                    elif provider == "1file":
                        onefile += 1

        matched += 1

    output = dict(catalog)
    output["catalog_import"] = {
        "schema_version": "1.0",
        "source": args.source_url or str(args.source),
        "notes": "Imported already-published host URLs; no FileCrypt/anti-bot resolution performed.",
    }
    output["games"] = games

    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("========================================")
    print("IMPORTAÇÃO DE DOWNLOADS")
    print("========================================")
    print(f"Jogos no catálogo local: {len(games)}")
    print(f"Jogos com correspondência: {matched}")
    print(f"Jogos sem correspondência: {unmatched}")
    print(f"URLs novas importadas: {imported_urls}")
    print(f"  MediaFire: {mediafire}")
    print(f"  1File/1fichier: {onefile}")
    print(f"Saída: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
