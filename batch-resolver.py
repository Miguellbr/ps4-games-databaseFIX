#!/usr/bin/env python3
"""
Batch FileCrypt Resolver - Resolve múltiplos links em paralelo
"""

import json
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from dataclasses import asdict
import time

from filecrypt_bypass import FileCryptBypass, BypassResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchResolver:
    def __init__(self, max_workers: int = 5, delay: float = 1.0):
        self.max_workers = max_workers
        self.delay = delay  # Delay entre requisições para não sobrecarregar
        self.results = {}
        self.errors = {}
        
    def resolve_single(self, game_id: str, filecrypt_url: str) -> Optional[str]:
        """Resolve um único link FileCrypt"""
        try:
            logger.info(f"[{game_id}] Resolvendo: {filecrypt_url[:60]}...")
            
            bypass = FileCryptBypass()
            result = bypass.bypass(filecrypt_url)
            
            if result.success and result.final_url:
                logger.info(f"[{game_id}] ✓ Sucesso: {result.final_url[:60]}...")
                return result.final_url
            else:
                logger.error(f"[{game_id}] ✗ Falha: {result.error_message}")
                self.errors[game_id] = {
                    'url': filecrypt_url,
                    'error': result.error_message,
                    'evidence': result.evidence_log
                }
                return None
                
        except Exception as e:
            logger.error(f"[{game_id}] ✗ Exceção: {e}")
            self.errors[game_id] = {
                'url': filecrypt_url,
                'error': str(e)
            }
            return None
            
    def resolve_batch(self, links_map: Dict[str, str]) -> Dict[str, str]:
        """
        Resolve múltiplos links em paralelo
        
        Args:
            links_map: {game_id: filecrypt_url}
            
        Returns:
            {game_id: direct_url}
        """
        successful = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submete todas as tarefas
            future_to_game = {
                executor.submit(self.resolve_single, game_id, url): game_id 
                for game_id, url in links_map.items()
            }
            
            # Processa resultados conforme completam
            for future in as_completed(future_to_game):
                game_id = future_to_game[future]
                try:
                    direct_url = future.result()
                    if direct_url:
                        successful[game_id] = direct_url
                    time.sleep(self.delay)  # Rate limiting
                except Exception as e:
                    logger.error(f"[{game_id}] Erro no future: {e}")
                    
        return successful
        
    def save_results(self, output_path: Path, successful: Dict[str, str]):
        """Salva resultados em JSON"""
        data = {
            'metadata': {
                'total_resolved': len(successful),
                'total_errors': len(self.errors),
                'timestamp': time.time()
            },
            'direct_links': successful,
            'errors': self.errors
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Resultados salvos em: {output_path}")
        logger.info(f"Sucessos: {len(successful)}, Erros: {len(self.errors)}")


def load_games_data(games_json_path: Path) -> Dict[str, str]:
    """
    Extrai links FileCrypt do seu games.json
    Adaptar conforme a estrutura do seu arquivo
    """
    with open(games_json_path, 'r', encoding='utf-8') as f:
        games = json.load(f)
        
    filecrypt_links = {}
    
    # Adaptar conforme a estrutura do seu JSON
    # Exemplo se games for uma lista:
    if isinstance(games, list):
        for game in games:
            game_id = str(game.get('id', game.get('title', 'unknown')))
            
            # Procura links FileCrypt em vários campos possíveis
            for field in ['download_url', 'filecrypt_url', 'link', 'url']:
                url = game.get(field, '')
                if url and 'filecrypt' in url.lower():
                    filecrypt_links[game_id] = url
                    break
                    
            # Ou procura em um array de links
            if 'links' in game:
                for link in game['links']:
                    if isinstance(link, dict) and 'filecrypt' in link.get('url', '').lower():
                        filecrypt_links[f"{game_id}_{link.get('id', '0')}"] = link['url']
                    elif isinstance(link, str) and 'filecrypt' in link.lower():
                        filecrypt_links[game_id] = link
                        
    # Exemplo se games for um dict:
    elif isinstance(games, dict):
        for game_id, game_data in games.items():
            if isinstance(game_data, dict):
                for field in ['download_url', 'filecrypt_url', 'link', 'url']:
                    url = game_data.get(field, '')
                    if url and 'filecrypt' in url.lower():
                        filecrypt_links[game_id] = url
                        break
                        
    logger.info(f"Encontrados {len(filecrypt_links)} links FileCrypt em {games_json_path}")
    return filecrypt_links


if __name__ == "__main__":
    import sys
    
    # Configurações
    GAMES_JSON = Path("data/games.json")  # Ajuste conforme seu arquivo
    OUTPUT_JSON = Path("data/direct_links.json")
    
    # Limitar quantidade para teste (opcional)
    TEST_LIMIT = None  # ou 10 para testar com 10 links apenas
    
    if not GAMES_JSON.exists():
        print(f"Erro: Arquivo não encontrado: {GAMES_JSON}")
        print("Ajuste o caminho em GAMES_JSON")
        sys.exit(1)
        
    # Carrega links FileCrypt
    links_map = load_games_data(GAMES_JSON)
    
    if TEST_LIMIT:
        links_map = dict(list(links_map.items())[:TEST_LIMIT])
        print(f"Modo TESTE: resolvendo apenas {TEST_LIMIT} links")
        
    if not links_map:
        print("Nenhum link FileCrypt encontrado!")
        sys.exit(1)
        
    # Resolve em batch
    resolver = BatchResolver(max_workers=3, delay=2.0)  # 3 workers, 2s delay
    successful = resolver.resolve_batch(links_map)
    
    # Salva resultados
    resolver.save_results(OUTPUT_JSON, successful)
    
    print(f"\nConcluído! Verifique {OUTPUT_JSON}")