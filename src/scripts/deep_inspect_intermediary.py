#!/usr/bin/env python3
"""Inspeção passiva aprofundada de uma página intermediária.

Somente GET. Não executa JavaScript, não envia POST e não tenta resolver
CAPTCHA/PoW. Salva HTML bruto e estrutura observável para análise.
"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


class DeepInspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.iframes = []
        self.forms = []
        self.inputs = []
        self.links = []
        self.metas = []
        self.data_attrs = []
        self._script = False
        self._script_buf = []
        self._script_src = None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        low = tag.lower()

        if low == "script":
            self._script = True
            self._script_buf = []
            self._script_src = d.get("src")

        if low == "iframe" and d.get("src"):
            self.iframes.append(d["src"])

        if low == "form":
            self.forms.append({
                "action": d.get("action"),
                "method": d.get("method"),
                "attrs": d,
            })

        if low == "input":
            self.inputs.append({
                "type": d.get("type"),
                "name": d.get("name"),
                "value": d.get("value"),
                "attrs": d,
            })

        if low == "a" and d.get("href"):
            self.links.append(d["href"])

        if low == "meta":
            self.metas.append(d)

        for k, v in attrs:
            if k.lower().startswith("data-") and v is not None:
                self.data_attrs.append({"name": k, "value": v})

    def handle_data(self, data):
        if self._script:
            self._script_buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._script:
            self.scripts.append({
                "src": self._script_src,
                "inline": "".join(self._script_buf)[:50000],
            })
            self._script = False
            self._script_buf = []
            self._script_src = None


def unique(values):
    out, seen = [], set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--output", default="deep_intermediary_inspection.json")
    ap.add_argument("--html", default="deep_intermediary.html")
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.7",
    })

    r = s.get(args.url, timeout=30, allow_redirects=False, headers={"Referer": args.url})
    html = r.text or ""

    Path(args.html).write_text(html, encoding="utf-8", errors="ignore")

    p = DeepInspector()
    p.feed(html)

    absolute = unique(re.findall(r"https?://[^\s\"'<>]+", html, re.I))
    nav = []
    for pattern in (
        r"""(?:window\.)?location(?:\.href|\.assign|\.replace)?\s*(?:=|\()\s*['"]([^'"]+)['"]""",
        r"""(?:window\.)?open\s*\(\s*['"]([^'"]+)['"]""",
        r"""(?:fetch|XMLHttpRequest)\s*\([^'"]*['"]([^'"]+)['"]""",
    ):
        nav.extend(re.findall(pattern, html, re.I))

    meta_refresh = []
    for m in p.metas:
        if str(m.get("http-equiv", "")).lower() == "refresh" and m.get("content"):
            mm = re.search(r"url\s*=\s*(.+)$", m["content"], re.I)
            if mm:
                meta_refresh.append(mm.group(1).strip().strip("\"'"))

    resolved = lambda values: unique([urljoin(r.url, x) for x in values])

    destinations = [
        u for u in absolute
        if any(host in urlparse(u).netloc.lower()
               for host in ("mediafire.com", "1file.com", "1fichier.com", "mega.nz"))
    ]

    result = {
        "requested_url": args.url,
        "status_code": r.status_code,
        "response_url": r.url,
        "location": r.headers.get("Location"),
        "content_type": r.headers.get("Content-Type", ""),
        "content_length": len(r.content or b""),
        "headers": {
            "server": r.headers.get("Server", ""),
            "cf_ray": r.headers.get("CF-Ray", ""),
        },
        "absolute_urls": absolute[:200],
        "known_destination_urls": destinations[:50],
        "navigation_references": resolved(nav)[:100],
        "meta_refresh": resolved(meta_refresh)[:50],
        "iframes": resolved(p.iframes)[:100],
        "forms": p.forms[:50],
        "inputs": p.inputs[:200],
        "links": resolved(p.links)[:200],
        "data_attributes": p.data_attrs[:300],
        "scripts": [
            {
                "src": urljoin(r.url, x["src"]) if x["src"] else None,
                "inline_length": len(x["inline"]),
                "inline": x["inline"],
            }
            for x in p.scripts
        ],
    }

    # Linhas úteis para leitura rápida, sem executar o conteúdo.
    signals = (
        "location", "redirect", "download", "mediafire", "1fichier",
        "1file", "mega.nz", "iframe", "form", "submit", "fetch(",
        "xmlhttprequest", "atob(", "decodeuri", "window.open",
    )
    result["interesting_lines"] = [
        line.strip()[:1000]
        for line in html.splitlines()
        if any(x in line.lower() for x in signals)
    ][:100]

    Path(args.output).write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 60)
    print("INSPEÇÃO PROFUNDA PASSIVA")
    print("=" * 60)
    print(f"HTTP: {r.status_code}")
    print(f"URL: {r.url}")
    print(f"HTML: {len(html)} bytes")
    print(f"Location HTTP: {r.headers.get('Location') or '-'}")
    print(f"Scripts: {len(p.scripts)}")
    print(f"Iframes: {len(p.iframes)}")
    print(f"Forms: {len(p.forms)}")
    print(f"Inputs: {len(p.inputs)}")
    print(f"Links: {len(p.links)}")
    print(f"Data-* : {len(p.data_attrs)}")
    print(f"URLs absolutas: {len(absolute)}")
    print(f"Destinos conhecidos: {len(destinations)}")

    if destinations:
        print("\n--- DESTINOS CONHECIDOS ---")
        for x in destinations[:50]:
            print(x)

    print("\n--- SCRIPTS ---")
    for i, x in enumerate(result["scripts"], 1):
        print(f"[{i}] SRC: {x['src'] or '(inline)'} | {x['inline_length']} bytes")

    print("\n--- IFRAMES ---")
    for x in result["iframes"]:
        print(x)

    print("\n--- FORMS ---")
    for x in result["forms"]:
        print(json.dumps(x, ensure_ascii=False))

    print("\n--- NAVEGAÇÃO / META ---")
    for x in result["navigation_references"] + result["meta_refresh"]:
        print(x)

    print("\n--- LINHAS INTERESSANTES ---")
    for x in result["interesting_lines"][:30]:
        print(x)

    print(f"\nHTML salvo em: {args.html}")
    print(f"JSON salvo em: {args.output}")


if __name__ == "__main__":
    main()
