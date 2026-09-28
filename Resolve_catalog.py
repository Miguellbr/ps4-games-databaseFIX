#!/usr/bin/env python3
"""
Resolve FileCrypt links no catalog.json
Gera resolved_links.json para uso no frontend
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from filecrypt_bypass import FileCryptBypass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_filecrypt_from_catalog(catalog_path: Path) -> Dict[str, dict]:
    """
    Extrai todos os links FileCrypt do catalog.json
    Retorna: {link_id: {game_title, host, index, url}}
    """
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    
    games = catalog.get('games', [])
    filecrypt_links = {}
    
    for game in games:
        title = game.get('title', 'unknown')
        dlps_url = game.get('dlps_url', '')
        
        # Se houver download_links (dados importados/normalizados)
        download_links = game.get('download_links', {})
        
        for host in ['mediafire', '1file', 'other', 'pkg']:
            urls = download_links.get(host, [])
            if not isinstance(urls, list):
                urls = [urls] if urls else []
            
            for idx, url in enumerate(urls):
                if url and 'filecrypt' in url.lower():
                    link_id = f"{title}__{host}__{idx}"
                    filecrypt_links[link_id] = {
                        'game_title': title,
                        'title_id': game.get('title_id', ''),
                        'host': host,
                        'index': idx,
                        'url': url,
                        'dlps_url': dlps_url
                    }
                    logger.info(f"Found FileCrypt: {link_id}")
    
    return filecrypt_links


def resolve_filecrypt_links(links_map: Dict[str, dict]) -> Dict[str, str]:
    """Resolve FileCrypt links para diretos"""
    resolved = {}
    
    for link_id, info in links_map.items():
        try:
            logger.info(f"Resolving: {link_id}")
            bypass = FileCryptBypass()
            result = bypass.bypass(info['url'])
            
            if result.success and result.final_url:
                resolved[link_id] = result.final_url
                logger.info(f"✓ Resolved: {result.final_url[:60]}...")
            else:
                logger.error(f"✗ Failed {link_id}: {result.error_message}")
                
        except Exception as e:
            logger.error(f"✗ Exception {link_id}: {e}")
    
    return resolved


def generate_resolved_json(
    links_map: Dict[str, dict], 
    resolved: Dict[str, str],
    output_path: Path
):
    """Gera resolved_links.json no formato para frontend"""
    
    data = {
        "metadata": {
            "total_found": len(links_map),
            "total_resolved": len(resolved),
            "timestamp": __import__('time').time(),
            "version": "1.0"
        },
        "resolutions": {}
    }
    
    for link_id, info in links_map.items():
        data["resolutions"][link_id] = {
            "original_url": info['url'],
            "direct_url": resolved.get(link_id),
            "resolved": link_id in resolved,
            "game_title": info['game_title'],
            "title_id": info['title_id'],
            "host": info['host'],
            "index": info['index']
        }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved: {output_path}")
    logger.info(f"Resolved: {len(resolved)}/{len(links_map)}")


def update_catalog_with_resolved(
    catalog_path: Path,
    resolved_path: Path,
    output_path: Path
):
    """(Opcional) Atualiza catalog.json substituindo FileCrypts por diretos"""
    
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
                if link_id in resolutions and resolutions[link_id].get('direct_url'):
                    new_urls.append(resolutions[link_id]['direct_url'])
                    logger.info(f"Replaced {link_id}")
                else:
                    new_urls.append(url)
            
            download_links[host] = new_urls
        
        game['download_links'] = download_links
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Updated catalog saved: {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Resolve FileCrypt in catalog")
    parser.add_argument('--catalog', default='catalog.json')
    parser.add_argument('--output', default='src/data/resolved_links.json')
    parser.add_argument('--update-catalog', action='store_true')
    parser.add_argument('--test', action='store_true', help='Test with 3 links')
    
    args = parser.parse_args()
    
    # Extract
    links = extract_filecrypt_from_catalog(Path(args.catalog))
    logger.info(f"Found {len(links)} FileCrypt links")
    
    if not links:
        logger.info("No FileCrypt links found.")
        exit(0)
    
    # Test mode
    if args.test:
        links = dict(list(links.items())[:3])
        logger.info(f"Test mode: {len(links)} links")
    
    # Resolve
    resolved = resolve_filecrypt_links(links)
    
    # Generate JSON
    generate_resolved_json(links, resolved, Path(args.output))
    
    # Optional: update catalog
    if args.update_catalog:
        update_catalog_with_resolved(
            Path(args.catalog),
            Path(args.output),
            Path('catalog_resolved.json')
        )