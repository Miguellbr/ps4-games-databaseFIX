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
from pathlib import Path

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

    @staticmethod
    def _inspect_html(html: str, base_url: str) -> Dict[str, Any]:
        """Inspeciona passivamente o HTML em busca de destinos e endpoints expostos.

        Não executa JavaScript, não resolve CAPTCHA/PoW e não envia requisições
        adicionais. O objetivo é descobrir o que a própria resposta HTML revela.
        """
        from html.parser import HTMLParser

        class Inspector(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.items = []
                self.in_script = False
                self.script_chunks = []

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                interesting = {
                    key: value for key, value in attrs_dict.items()
                    if key in ('href', 'src', 'action', 'value', 'data-url',
                               'data-link', 'data-href', 'data-target', 'data-destination')
                    and value
                }
                if interesting:
                    self.items.append({'tag': tag, 'attrs': interesting})
                if tag.lower() == 'script':
                    self.in_script = True
                    self.script_chunks = []

            def handle_endtag(self, tag):
                if tag.lower() == 'script' and self.in_script:
                    text = ''.join(self.script_chunks)
                    if text.strip():
                        self.items.append({'tag': 'script', 'text': text[:20000]})
                    self.in_script = False
                    self.script_chunks = []

            def handle_data(self, data):
                if self.in_script:
                    self.script_chunks.append(data)

        parser = Inspector()
        try:
            parser.feed(html or '')
        except Exception:
            pass

        # URLs absolutas encontradas literalmente na resposta.
        raw_urls = re.findall(r"https?://[^\\s\"'<>]+", html or '', re.IGNORECASE)
        urls = []
        seen = set()
        for raw in raw_urls:
            value = raw.rstrip('.,;)]}')
            if value and value not in seen:
                seen.add(value)
                urls.append(value)

        # Endpoints internos do FileCrypt, como /Link/1, /Link/2, etc.
        internal_links = sorted(set(re.findall(r"/Link/\\d+(?:[^\\s\"'<>]*)?", html or '', re.IGNORECASE)))

        # Scripts relevantes para entender o fluxo, sem executá-los.
        scripts = sorted(set(re.findall(
            r'(?:src|href)=["\\\']([^"\\\']*(?:container(?:/link)?|pow_captcha)[^"\\\']*)',
            html or '', re.IGNORECASE
        )))

        candidate_urls = []
        for value in urls:
            parsed = urlparse(value)
            host = parsed.netloc.lower()
            if host and not host.endswith('filecrypt.cc'):
                candidate_urls.append(value)

        return {
            'base_url': base_url,
            'html_length': len(html or ''),
            'absolute_urls': urls,
            'external_url_candidates': candidate_urls,
            'internal_link_endpoints': internal_links,
            'relevant_scripts': scripts,
            'interesting_attributes': parser.items,
        }

    def inspect(self, filecrypt_url: str) -> Dict[str, Any]:
        """Baixa uma página e faz somente inspeção estática da resposta."""
        logger.info(f"[INSPECT] Analisando: {filecrypt_url}")
        try:
            response = self.session.get(
                filecrypt_url,
                timeout=30,
                allow_redirects=True,
                headers={'Referer': filecrypt_url}
            )
        except requests.RequestException as exc:
            result = {'success': False, 'error': f'Falha HTTP: {exc}'}
            self._log_evidence('inspection_error', result)
            return result

        html = response.text or ''
        inspection = self._inspect_html(html, response.url)
        inspection.update({
            'success': True,
            'status_code': response.status_code,
            'requested_url': filecrypt_url,
            'response_url': response.url,
            'redirect_history': [
                {'status': r.status_code, 'url': r.url, 'location': r.headers.get('Location')}
                for r in response.history
            ],
            'content_type': response.headers.get('Content-Type', ''),
        })
        self._log_evidence('static_inspection', inspection)
        return inspection

    def _extract_pow_params(self, html: str, url: str) -> Optional[PoWChallenge]:
        """Detecta desafios PoW de formato genérico, sem presumir o mecanismo específico."""
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
    def _detect_filecrypt_pow(html: str) -> Optional[Dict[str, Any]]:
        """Detecta especificamente o widget PoW/CAPTCHA exibido pelo FileCrypt."""
        text = html or ''
        lower = text.lower()

        signals = []
        if 'id="pow-captcha"' in lower or "id='pow-captcha'" in lower:
            signals.append('pow_captcha')
        if 'data-session="/captchasession/' in lower or "data-session='/captchasession/" in lower:
            signals.append('captcha_session')
        if '/js/pow_captcha.js' in lower:
            signals.append('pow_captcha_js')
        if 'data-worker="/js/pow_captcha_worker.js' in lower or "data-worker='/js/pow_captcha_worker.js" in lower:
            signals.append('pow_captcha_worker')

        if len(signals) < 2:
            return None

        def attr(name: str) -> Optional[str]:
            match = re.search(
                rf'data-{re.escape(name)}\s*=\s*["\']([^"\']+)',
                text,
                re.IGNORECASE
            )
            return match.group(1) if match else None

        result = {
            'provider': 'filecrypt',
            'type': 'pow_captcha',
            'signals': signals,
            'session': attr('session'),
            'worker': attr('worker'),
            'text': attr('text-working'),
            'state': attr('state'),
        }

        return result

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
                r"""https?://[^"'<>s]+(?:mediafire.com|1file.com|1fichier.com)[^"'<>s]*""",
                r"""(?:href|data-url|location|redirect|url)s*=s*["'](https?://[^"']+)"""
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

    def save_session(self, path: str = 'filecrypt_session.json') -> str:
        """Salva cookies e metadados da sessão em JSON para retomada manual."""
        payload = {
            'version': 1,
            'saved_at': time.time(),
            'cookies': [
                {
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path,
                    'secure': cookie.secure,
                    'expires': cookie.expires
                }
                for cookie in self.session.cookies
            ],
            'headers': {'User-Agent': self.session.headers.get('User-Agent', '')}
        }
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        self._log_evidence('session_saved', {'path': str(output), 'cookies': len(payload['cookies'])})
        return str(output)

    def load_session(self, path: str = 'filecrypt_session.json') -> int:
        """Restaura cookies previamente salvos; não executa nenhuma verificação."""
        input_path = Path(path)
        with input_path.open('r', encoding='utf-8') as f:
            payload = json.load(f)
        cookies = payload.get('cookies', [])
        restored = 0
        for item in cookies:
            if not item.get('name') or item.get('value') is None:
                continue
            self.session.cookies.set(
                item['name'], item['value'],
                domain=item.get('domain') or '',
                path=item.get('path') or '/'
            )
            restored += 1
        self._log_evidence('session_loaded', {'path': str(input_path), 'cookies': restored})
        return restored

    def _result_after_session_refresh(self, filecrypt_url: str, attempt: int) -> Optional[BypassResult]:
        """Tenta novamente usando a mesma sessão/cookies já existentes.

        Não resolve nem contorna desafios. Serve para continuar uma sessão
        depois que a verificação foi concluída fora deste resolver.
        """
        try:
            response = self.session.get(
                filecrypt_url,
                timeout=30,
                allow_redirects=True,
                headers={'Referer': filecrypt_url}
            )
            html = response.text or ''
            self._log_evidence('session_refresh', {
                'attempt': attempt,
                'status': response.status_code,
                'url': response.url,
                'content_length': len(html),
                'cookies': list(self.session.cookies.keys())
            })

            direct = self._find_final_url(response) or self._extract_final_link({}, html)
            if direct:
                return BypassResult(
                    success=True,
                    final_url=direct,
                    response_data={'attempt': attempt, 'url': response.url},
                    cookies=dict(self.session.cookies),
                    evidence_log=self.evidence_log
                )
            return None
        except requests.RequestException as e:
            self._log_evidence('session_refresh_error', {
                'attempt': attempt,
                'error': str(e)
            })
            return None

    def retry_after_verification(self, filecrypt_url: str, attempts: int = 1) -> BypassResult:
        """Retoma a mesma sessão após uma verificação feita externamente.

        Não executa CAPTCHA/PoW. Apenas reutiliza os cookies da sessão atual
        e verifica se o FileCrypt já liberou um destino explícito.
        """
        attempts = max(1, min(int(attempts), 3))
        for attempt in range(1, attempts + 1):
            result = self._result_after_session_refresh(filecrypt_url, attempt)
            if result:
                return result

        return BypassResult(
            success=False,
            error_message='needs_verification: sessão ainda não liberada pelo FileCrypt',
            response_data={'url': filecrypt_url, 'attempts': attempts},
            cookies=dict(self.session.cookies),
            evidence_log=self.evidence_log
        )

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
                ],
                'content_type': response.headers.get('Content-Type', ''),
                'content_encoding': response.headers.get('Content-Encoding', ''),
                'server': response.headers.get('Server', ''),
                'cf_ray': response.headers.get('CF-Ray', '')
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

        filecrypt_pow = self._detect_filecrypt_pow(html)
        if filecrypt_pow:
            self._log_evidence('filecrypt_pow_challenge', filecrypt_pow)
            return BypassResult(
                success=False,
                error_message='needs_verification: FileCrypt PoW/CAPTCHA detectado',
                response_data={
                    'status_code': response.status_code,
                    'url': response.url,
                    'challenge': filecrypt_pow
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
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Inspeciona e retoma sessões FileCrypt após verificação manual.'
    )
    parser.add_argument('url', help='URL do Container FileCrypt')
    parser.add_argument('--session', default='filecrypt_session.json',
                        help='Arquivo JSON usado para persistir os cookies da sessão')
    parser.add_argument('--load-session', action='store_true',
                        help='Carrega a sessão salva antes da requisição')
    parser.add_argument('--save-session', action='store_true',
                        help='Salva a sessão após a requisição')
    parser.add_argument('--retry', action='store_true',
                        help='Após a carga inicial, faz uma nova tentativa usando a mesma sessão')
    parser.add_argument('--attempts', type=int, default=1,
                        help='Número de tentativas no --retry (máx. 3)')
    parser.add_argument('--inspect', action='store_true',
                        help='Inspeciona estaticamente HTML/atributos/scripts sem tentar resolver CAPTCHA/PoW')
    args = parser.parse_args()

    bypass = FileCryptBypass()

    if args.inspect:
        inspection = bypass.inspect(args.url)
        print("\n" + "=" * 60)
        print("INSPEÇÃO ESTÁTICA DO FILECRYPT")
        print("=" * 60)
        print(f"HTTP: {inspection.get('status_code', '?')}")
        print(f"URL da resposta: {inspection.get('response_url', '?')}")
        print(f"HTML: {inspection.get('html_length', 0)} bytes")
        print(f"URLs absolutas: {len(inspection.get('absolute_urls', []))}")
        print(f"Candidatos externos: {len(inspection.get('external_url_candidates', []))}")
        print(f"Endpoints /Link/*: {len(inspection.get('internal_link_endpoints', []))}")
        print(f"Scripts relevantes: {len(inspection.get('relevant_scripts', []))}")
        print("\n--- CANDIDATOS EXTERNOS ---")
        for value in inspection.get('external_url_candidates', []):
            print(value)
        print("\n--- /Link/* ---")
        for value in inspection.get('internal_link_endpoints', []):
            print(value)
        print("\n--- SCRIPTS ---")
        for value in inspection.get('relevant_scripts', []):
            print(value)
        print("\n--- ATRIBUTOS INTERESSANTES ---")
        for item in inspection.get('interesting_attributes', []):
            print(json.dumps(item, ensure_ascii=False))
        with open('filecrypt_inspection.json', 'w', encoding='utf-8') as f:
            json.dump(inspection, f, indent=2, ensure_ascii=False)
        print("\nInspeção salva em: filecrypt_inspection.json")
        sys.exit(0)

    if args.load_session:
        try:
            restored = bypass.load_session(args.session)
            print(f'Sessão restaurada: {restored} cookies')
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f'Não foi possível carregar a sessão: {exc}')
            sys.exit(1)

    result = bypass.bypass(args.url)

    if args.save_session:
        try:
            saved = bypass.save_session(args.session)
            print(f'Sessão salva em: {saved}')
        except OSError as exc:
            print(f'Não foi possível salvar a sessão: {exc}')

    if args.retry and not result.success:
        print('\nTentando retomar a mesma sessão...')
        result = bypass.retry_after_verification(args.url, args.attempts)

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
    with open('bypass_evidence.json', 'w', encoding='utf-8') as f:
        json.dump(result.evidence_log, f, indent=2, default=str, ensure_ascii=False)
    print("Evidências salvas em: bypass_evidence.json")
