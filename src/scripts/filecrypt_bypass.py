#!/usr/bin/env python3
"""
FileCrypt Bypass - Puro Python (no sandbox, no rendering)
Resolve PoW via HTTP requests e extrai link final do MediaFire/1File
"""

import requests
import hashlib
import re
import json
import time
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PoWChallenge:
    """Representa um desafio PoW detectado"""
    pow_id: str
    algorithm: str
    difficulty: int
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class BypassResult:
    """Resultado do bypass"""
    success: bool
    final_url: Optional[str] = None
    error_message: Optional[str] = None
    response_data: Optional[Dict] = None
    cookies: Optional[Dict] = None
    evidence_log: list = None

    def __post_init__(self):
        if self.evidence_log is None:
            self.evidence_log = []


class FileCryptBypass:
    """
    Bypass do FileCrypt via HTTP puro - sem browser, sem JavaScript
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
        })
        self.evidence_log = []

    def _log_evidence(self, stage: str, data: Dict):
        """Registra evidência observável"""
        entry = {
            'timestamp': time.time(),
            'stage': stage,
            'data': data
        }
        self.evidence_log.append(entry)
        logger.debug(f"[EVIDENCE] {stage}: {json.dumps(data, indent=2)[:200]}...")

    def _extract_pow_params(self, html: str, url: str) -> Optional[PoWChallenge]:
        """Detecta desafios de verificação sem presumir um formato específico."""
        self._log_evidence('html_raw', {'length': len(html), 'url': url})

        lower = html.lower()
        markers = [
            'captcha', 'hcaptcha', 'recaptcha', 'turnstile',
            'cloudflare', 'verify you are human', 'verification',
            'challenge', 'pow', 'proof of work'
        ]
        detected = [m for m in markers if m in lower]

        def first(pattern):
            m = re.search(pattern, html, re.IGNORECASE)
            return m.group(1) if m else None

        pow_id = first(r"(?:name|id)=[\"']pow_id[\"'][^>]*value=[\"']([^\"']+)")
        algorithm = first(r"(?:name|id)=[\"']pow_algorithm[\"'][^>]*value=[\"']([^\"']+)")
        difficulty_raw = first(r"(?:name|id)=[\"']pow_difficulty[\"'][^>]*value=[\"'](\d+)")

        self._log_evidence('challenge_detection', {
            'markers': detected,
            'explicit_pow_id': bool(pow_id)
        })

        if not pow_id:
            return None

        return PoWChallenge(
            pow_id=pow_id,
            algorithm=(algorithm or 'unknown').lower(),
            difficulty=int(difficulty_raw or 0),
            prefix=first(r"(?:name|id)=[\"']pow_prefix[\"'][^>]*value=[\"']([^\"']*)") or '',
            suffix=first(r"(?:name|id)=[\"']pow_suffix[\"'][^>]*value=[\"']([^\"']*)") or '',
            extra_params={}
        )

    @staticmethod
    def _looks_like_verification(html: str) -> bool:
        text = (html or '').lower()
        return any(marker in text for marker in (
            'captcha', 'hcaptcha', 'recaptcha', 'turnstile',
            'cloudflare', 'verify you are human',
            'checking your browser', 'access denied',
            'verification required'
        ))

    @staticmethod
    def _detect_cloudflare_challenge(html: str) -> Optional[Dict[str, Any]]:
        """Detecta a página de Challenge do Cloudflare sem tentar contorná-la."""
        text = html or ''
        lower = text.lower()
        signals = []

        if '<title>just a moment...</title>' in lower:
            signals.append('just_a_moment')
        if 'window._cf_chl_opt' in lower:
            signals.append('cf_chl_opt')
        if '/cdn-cgi/challenge-platform/' in lower:
            signals.append('challenge_platform')
        if 'challenges.cloudflare.com' in lower:
            signals.append('challenges.cloudflare.com')

        if len(signals) < 2:
            return None

        ray = None
        match = re.search(r"""cRay:\s*['"]([^'"]+)""", text, re.IGNORECASE)
        if match:
            ray = match.group(1)

        return {
            'provider': 'cloudflare',
            'type': 'managed_challenge',
            'signals': signals,
            'ray': ray,
        }

    @staticmethod
    def _find_final_url(response: requests.Response) -> Optional[str]:
        """Retorna um destino final somente quando a requisição já o revelou."""
        url = response.url
        host = urlparse(url).netloc.lower()
        if any(h in host for h in ('mediafire.com', '1file.com', '1fichier.com')):
            return url
        return None

    def _extract_final_link(self, response_data: Dict, html: str) -> Optional[str]:
        """Extrai destinos explícitos de respostas HTML/JSON."""
        candidates = []

        if isinstance(response_data, dict):
            for field in ('download_url', 'final_url', 'direct_link', 'url', 'link',
                          'redirect', 'location', 'mediafire', '1file', '1fichier'):
                value = response_data.get(field)
                if isinstance(value, str):
                    candidates.append(value)

        if html:
            patterns = [
                r"""https?://[^"'<>s]+(?:mediafire\.com|1file\.com|1fichier\.com)[^"'<>s]*""",
                r"""(?:href|data-url|location|redirect|url)\s*=\s*["'](https?://[^"']+)"""
            ]
            for pattern in patterns:
                candidates.extend(re.findall(pattern, html, re.IGNORECASE))

        for link in candidates:
            link = link.replace('&amp;', '&')
            if link.startswith(('http://', 'https://')) and any(
                host in urlparse(link).netloc.lower()
                for host in ('mediafire.com', '1file.com', '1fichier.com')
            ):
                return link

        return None

    def bypass(self, filecrypt_url: str) -> BypassResult:
        """
        Carrega o FileCrypt, segue redirecionamentos normais e extrai um destino
        explícito. Quando encontra anti-bot/verificação, retorna esse estado em
        vez de fingir que um endpoint ou payload é conhecido.
        """
        logger.info(f"[RESOLVE] Iniciando: {filecrypt_url}")

        try:
            response = self.session.get(filecrypt_url, timeout=30, allow_redirects=True)
            html = response.text or ''
            self._log_evidence('initial_load', {
                'status': response.status_code,
                'content_length': len(html),
                'requested_url': filecrypt_url,
                'final_response_url': response.url,
                'history': [
                    {'status': r.status_code, 'url': r.url, 'location': r.headers.get('Location')}
                    for r in response.history
                ]
            })
        except requests.RequestException as e:
            return BypassResult(
                success=False,
                error_message=f"Falha HTTP: {e}",
                evidence_log=self.evidence_log
            )

        direct = self._find_final_url(response) or self._extract_final_link({}, html)
        if direct:
            return BypassResult(
                success=True,
                final_url=direct,
                cookies=dict(self.session.cookies),
                evidence_log=self.evidence_log
            )

        cloudflare = self._detect_cloudflare_challenge(html)
        if cloudflare:
            self._log_evidence('cloudflare_challenge', cloudflare)
            return BypassResult(
                success=False,
                error_message='needs_verification: Cloudflare Challenge detectado',
                response_data={
                    'status_code': response.status_code,
                    'url': response.url,
                    'challenge': cloudflare
                },
                cookies=dict(self.session.cookies),
                evidence_log=self.evidence_log
            )

        if self._looks_like_verification(html):
            self._log_evidence('verification_required', {
                'url': response.url,
                'status': response.status_code
            })
            return BypassResult(
                success=False,
                error_message='needs_verification: a página exige verificação/anti-bot',
                response_data={'status_code': response.status_code, 'url': response.url},
                cookies=dict(self.session.cookies),
                evidence_log=self.evidence_log
            )

        challenge = self._extract_pow_params(html, response.url)
        if challenge:
            return BypassResult(
                success=False,
                error_message=(
                    f'needs_verification: desafio PoW detectado '
                    f'(algorithm={challenge.algorithm}, difficulty={challenge.difficulty})'
                ),
                response_data={'challenge': {
                    'pow_id': challenge.pow_id,
                    'algorithm': challenge.algorithm,
                    'difficulty': challenge.difficulty
                }},
                cookies=dict(self.session.cookies),
                evidence_log=self.evidence_log
            )

        return BypassResult(
            success=False,
            error_message='unknown: nenhum destino direto ou desafio reconhecido foi encontrado',
            response_data={
                'status_code': response.status_code,
                'url': response.url,
                'content_type': response.headers.get('Content-Type', '')
            },
            cookies=dict(self.session.cookies),
            evidence_log=self.evidence_log
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python filecrypt_bypass.py <url_filecrypt>")
        print("Exemplo: python filecrypt_bypass.py https://filecrypt.co/Container/ABC123.html")
        sys.exit(1)

    url = sys.argv[1]
    bypass = FileCryptBypass()
    result = bypass.bypass(url)

    print("\n" + "="*60)
    print("RESULTADO DO BYPASS")
    print("="*60)
    print(f"Sucesso: {result.success}")

    if result.success:
        print(f"Link Final: {result.final_url}")
        print(f"Cookies: {result.cookies}")
    else:
        print(f"Erro: {result.error_message}")

    print(f"\nEvidências registradas: {len(result.evidence_log)} entradas")

    with open('bypass_evidence.json', 'w') as f:
        json.dump(result.evidence_log, f, indent=2, default=str)
    print("Evidências salvas em: bypass_evidence.json")
