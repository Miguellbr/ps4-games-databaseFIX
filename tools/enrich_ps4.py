#!/usr/bin/env python3
"""
Enriches the PS4 catalog with official PlayStation Store metadata.

The source catalog stays the same; this tool adds:
  cover_url
  description_en
  description_pt
  metadata_source
  metadata_content_id

It uses Sony's public Chihiro titlecontainer endpoints. A PS4 title ID such as
CUSA06027 is resolved as CUSA06027_00. English is requested from US/EN and
Portuguese from BR/PT, with PT-PT as a fallback.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://store.playstation.com/store/api/chihiro/00_09_000/titlecontainer"
LOCALES = (("us", "en", "en"), ("br", "pt", "pt"), ("pt", "pt", "pt_fallback"))
UA = "PS4-Games-Database-Metadata/1.0"

def clean_title_id(value):
    s = str(value or "").strip().upper()
    if s.endswith("_00"):
        s = s[:-3]
    m = re.search(r"(CUSA\d{5})", s)
    return m.group(1) if m else ""

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def text_value(value):
    if isinstance(value, str):
        v = re.sub(r"\\s+", " ", value).strip()
        return v if v else ""
    return ""

def first_key(node, keys):
    if isinstance(node, dict):
        for key in keys:
            v = text_value(node.get(key))
            if v:
                return v
        for value in node.values():
            v = first_key(value, keys)
            if v:
                return v
    elif isinstance(node, list):
        for value in node:
            v = first_key(value, keys)
            if v:
                return v
    return ""

def first_product_id(node):
    keys = ("product_id", "productId", "content_id", "contentId", "id")
    if isinstance(node, dict):
        for key in keys:
            v = text_value(node.get(key))
            if "-" in v and len(v) >= 25:
                return v
        for value in node.values():
            v = first_product_id(value)
            if v:
                return v
    elif isinstance(node, list):
        for value in node:
            v = first_product_id(value)
            if v:
                return v
    return ""

def fetch_locale(title_id, country, language):
    tid = clean_title_id(title_id)
    if not tid:
        return None
    url = f"{BASE}/{country}/{language}/999/{tid}_00"
    try:
        data = get_json(url)
    except Exception:
        return None
    desc = first_key(data, ("description", "long_description", "short_description"))
    name = first_key(data, ("name", "title"))
    product_id = first_product_id(data)
    return {"description": desc, "name": name, "product_id": product_id} if (desc or name or product_id) else None

def enrich_game(game, delay):
    tid = clean_title_id(game.get("title_id"))
    if not tid:
        return {}
    result = {"metadata_source": "PlayStation Store", "metadata_title_id": tid}

    en = fetch_locale(tid, "us", "en")
    time.sleep(delay)

    pt = fetch_locale(tid, "br", "pt")
    time.sleep(delay)

    if not pt:
        pt = fetch_locale(tid, "pt", "pt")
        time.sleep(delay)

    if en and en.get("description"):
        result["description_en"] = en["description"]
    if pt and pt.get("description"):
        result["description_pt"] = pt["description"]

    # The titlecontainer image endpoint is stable and does not require a
    # product/content slug, only the PS4 title ID.
    result["cover_url"] = f"{BASE}/us/en/999/{tid}_00/image"
    result["metadata_content_id"] = (en or pt or {}).get("product_id", "")
    return result

def find_games(data):
    if isinstance(data, list):
        if any(isinstance(x, dict) and ("title_id" in x or "name" in x) for x in data):
            return data
        for x in data:
            found = find_games(x)
            if found is not None:
                return found
    elif isinstance(data, dict):
        if isinstance(data.get("DATA"), dict):
            return list(data["DATA"].values())
        if isinstance(data.get("games"), list):
            return data["games"]
        for x in data.values():
            found = find_games(x)
            if found is not None:
                return found
    return None

def load_games(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_game_refs(data):
    if isinstance(data, dict) and isinstance(data.get("DATA"), dict):
        return [(i, v) for i, v in enumerate(data["DATA"].values())]
    games = find_games(data)
    return list(enumerate(games or []))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("part")
    p.add_argument("--input", required=True)
    p.add_argument("--part", type=int, required=True)
    p.add_argument("--parts", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--delay", type=float, default=0.65)

    m = sub.add_parser("merge")
    m.add_argument("--input", required=True)
    m.add_argument("--parts-dir", required=True)
    m.add_argument("--output", required=True)

    args = ap.parse_args()
    data = load_games(args.input)

    if args.mode == "part":
        refs = get_game_refs(data)
        selected = refs[args.part::args.parts]
        results = []
        for index, game in selected:
            if not isinstance(game, dict):
                continue
            try:
                meta = enrich_game(game, args.delay)
            except Exception as exc:
                print(f"metadata failed at index {index}: {exc}", file=sys.stderr)
                meta = {}
            results.append({"index": index, "metadata": meta})
            if index % 50 == 0:
                print(f"part {args.part}: processed index {index}", flush=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, separators=(",", ":"))
        return

    # Merge: support DATA objects and plain game arrays.
    parts = []
    for name in sorted(os.listdir(args.parts_dir)):
        if name.endswith(".json"):
            with open(os.path.join(args.parts_dir, name), "r", encoding="utf-8") as f:
                parts.extend(json.load(f))

    by_index = {int(x["index"]): x.get("metadata", {}) for x in parts}
    if isinstance(data, dict) and isinstance(data.get("DATA"), dict):
        values = list(data["DATA"].values())
        for i, game in enumerate(values):
            if isinstance(game, dict):
                game.update({k:v for k,v in by_index.get(i, {}).items() if v})
    else:
        games = find_games(data)
        if games is None:
            raise SystemExit("Could not locate the game array/DATA object.")
        for i, game in enumerate(games):
            if isinstance(game, dict):
                game.update({k:v for k,v in by_index.get(i, {}).items() if v})

    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, args.output)
    print(f"Merged metadata for {len(by_index):,} records.")

if __name__ == "__main__":
    main()
