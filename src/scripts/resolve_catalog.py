#!/usr/bin/env python3
"""
Resolve FileCrypt links no catalog.json
Gera resolved_links.json para uso no frontend.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any
from filecrypt_bypass import FileCryptBypass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_filecrypt_from_catalog(catalog_path: Path) -> Dict[str, dict]:
    """Extrai links FileCrypt dos formatos usados pelo projeto."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    filecrypt_links = {}

    def add_game(game: dict):
        title = game.get('title') or game.get('name') or game.get('game_name') or 'unknown'
        dlps_url = game.get('dlps_url', '')
        download_links = game.get('download_links') or {}

        for host in ['mediafire', '1file', 'other', 'pkg']:
            urls = download_links.get(host, [])
            if not isinstance(urls, list):
                urls = [urls] if urls else []
            for idx, url in enumerate(urls):
                if isinstance(url, str) and 'filecrypt' in url.lower():
                    link_id = f"{title}__{host}__{idx}"
                    filecrypt_links[link_id] = {
                        'game_title': title,
                        'title_id': game.get('title_id') or game.get('titleId') or '',
                        'host': host,
                        'index': idx,
                        'url': url,
                        'dlps_url': dlps_url
                    }
                    logger.info(f"Found FileCrypt: {link_id}")

    if isinstance(data, dict) and isinstance(data.get('DATA'), dict):
        for url, item in data['DATA'].items():
            item = dict(item) if isinstance(item, dict) else {}
            links = item.get('download_links') or {}
            if not links and url:
                links = {'pkg': [url]}
            item['download_links'] = links
            add_game(item)
    elif isinstance(data, dict) and isinstance(data.get('games'), list):
        for game in data['games']:
            if isinstance(game, dict):
                add_game(game)
    elif isinstance(data, list):
        for game in data:
            if isinstance(game, dict):
                add_game(game)

    return filecrypt_links


def resolve_filecrypt_links(links_map: Dict[str, dict]) -> Dict[str, dict]:
    """
    Executa o resolver existente e preserva o estado de cada tentativa.
    Assim, falhas como needs_verification não desaparecem do resultado.
    """
    results = {}

    for link_id, info in links_map.items():
        try:
            logger.info(f"Resolving: {link_id}")
            bypass = FileCryptBypass()
            result = bypass.bypass(info['url'])

            if result.success and result.final_url:
                results[link_id] = {
                    'status': 'resolved',
                    'resolved': True,
                    'direct_url': result.final_url,
                    'error': None
                }
                logger.info(f"✓ Resolved: {result.final_url[:60]}...")
            else:
                error = result.error_message or 'unknown'
                status = 'needs_verification' if error.startswith('needs_verification:') else 'error'
                results[link_id] = {
                    'status': status,
                    'resolved': False,
                    'direct_url': None,
                    'error': error
                }
                logger.warning(f"• {status} {link_id}: {error}")

        except Exception as e:
            results[link_id] = {
                'status': 'error',
                'resolved': False,
                'direct_url': None,
                'error': str(e)
            }
            logger.exception(f"✗ Exception {link_id}")

    return results


def generate_resolved_json(
    links_map: Dict[str, dict],
    results: Dict[str, dict],
    output_path: Path
):
    """Gera resolved_links.json com estado explícito de cada link."""

    resolved_count = sum(1 for item in results.values() if item.get('resolved'))
    verification_count = sum(
        1 for item in results.values()
        if item.get('status') == 'needs_verification'
    )

    data = {
        'metadata': {
            'total_found': len(links_map),
            'total_resolved': resolved_count,
            'total_needs_verification': verification_count,
            'total_errors': sum(1 for item in results.values() if item.get('status') == 'error'),
            'timestamp': time.time(),
            'version': '1.1'
        },
        'resolutions': {}
    }

    for link_id, info in links_map.items():
        result = results.get(link_id, {
            'status': 'unknown',
            'resolved': False,
            'direct_url': None,
            'error': 'no result'
        })

        data['resolutions'][link_id] = {
            'original_url': info['url'],
            'direct_url': result.get('direct_url'),
            'resolved': bool(result.get('resolved')),
            'status': result.get('status', 'unknown'),
            'error': result.get('error'),
            'game_title': info['game_title'],
            'title_id': info['title_id'],
            'host': info['host'],
            'index': info['index']
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved: {output_path}")
    logger.info(
        f"Resolved: {resolved_count}/{len(links_map)} | "
        f"Needs verification: {verification_count}"
    )


def update_catalog_with_resolved(
    catalog_path: Path,
    resolved_path: Path,
    output_path: Path
):
    """Atualiza opcionalmente o catálogo, substituindo somente links resolvidos."""

    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    with open(resolved_path, 'r', encoding='utf-8') as f:
        resolved_data = json.load(f)

    resolutions = resolved_data.get('resolutions', {})

    for game in catalog.get('games', []):
        title = game.get('title', '')
        download_links = game.get('download_links', {})

        for host in ['mediafire', '1file', 'other', 'pkg']:
            urls = download_links.get(host, [])
            if not isinstance(urls, list):
                urls = [urls] if urls else []

            new_urls = []
            for idx, url in enumerate(urls):
                link_id = f"{title}__{host}__{idx}"
                direct_url = resolutions.get(link_id, {}).get('direct_url')
                new_urls.append(direct_url or url)

            download_links[host] = new_urls

        game['download_links'] = download_links

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    logger.info(f"Updated catalog saved: {output_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Resolve FileCrypt in catalog')
    parser.add_argument('--catalog', default='ps4_games_expanded.json')
    parser.add_argument('--output', default='src/data/resolved_links.json')
    parser.add_argument('--update-catalog', action='store_true')
    parser.add_argument('--test', action='store_true', help='Test with 3 links')

    args = parser.parse_args()

    links = extract_filecrypt_from_catalog(Path(args.catalog))
    logger.info(f"Found {len(links)} FileCrypt links")

    if not links:
        logger.info('No FileCrypt links found.')
        raise SystemExit(0)

    if args.test:
        links = dict(list(links.items())[:3])
        logger.info(f"Test mode: {len(links)} links")

    results = resolve_filecrypt_links(links)
    generate_resolved_json(links, results, Path(args.output))

    if args.update_catalog:
        update_catalog_with_resolved(
            Path(args.catalog),
            Path(args.output),
            Path('catalog_resolved.json')
        )
