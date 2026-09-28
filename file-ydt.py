import asyncio
import json
import uuid
import time
from datetime import datetime
from playwright.async_api import async_playwright
import re
import os


class FileCryptAnalyzer:
    """
    Análise completa do fluxo FileCrypt CAPTCHA.
    Documenta reproduzivelmente todo o fluxo sem assumir nada.
    """

    def __init__(self):
        # Inicialização completa de todas as variáveis
        self.scripts = {}
        self.scripts_content = {}  # Conteúdo completo preservado
        self.network_log = []
        self.request_map = {}  # UUID -> request entry
        self.captcha_requests = []  # Requests marcadas como relacionadas
        self.worker_messages = []
        self.form_fields_log = []
        self.dom_events = []
        self.validation_events = []
        self.completion_signals = []
        self.session_data = {}
        self.captcha_config = {}
        self._last_form_snapshot = None
        self._captcha_completed = False

    async def run_analysis(self, container_url):
        """Fluxo único: setup → navegação → monitoramento → análise"""
        
        print("=" * 70)
        print("FILECRYPT ANALYZER - Análise de Fluxo Real")
        print("=" * 70)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=['--window-size=1400,900', '--disable-web-security']
            )
            
            context = await browser.new_context(
                viewport={'width': 1400, 'height': 900}
            )
            
            page = await context.new_page()
            
            # ============================================
            # SETUP: Todos os interceptadores ANTES da navegação
            # ============================================
            print("\n[SETUP] Configurando interceptadores...")
            await self._setup_network_interceptors(page)
            await self._setup_worker_interception(page)
            await self._setup_form_monitoring(page)
            await self._setup_mutation_observer(page)
            
            # ============================================
            # NAVEGAÇÃO ÚNICA
            # ============================================
            print(f"\n[NAV] Carregando: {container_url}")
            await page.goto(container_url, wait_until='networkidle')
            print("[NAV] Página carregada.")
            
            # ============================================
            # EXTRAÇÃO INICIAL
            # ============================================
            self.captcha_config = await self._extract_captcha_config(page)
            
            if not self.captcha_config.get('session'):
                print("[✗] CAPTCHA não encontrado na página")
                await browser.close()
                return
            
            # Snapshot inicial dos campos
            await self._capture_form_snapshot(page, "initial")
            
            # ============================================
            # DOWNLOAD DOS SCRIPTS
            # ============================================
            await self._download_scripts(page)
            
            # ============================================
            # MONITORAMENTO ATÉ CONCLUSÃO
            # ============================================
            print("\n" + "=" * 70)
            print("MONITORAMENTO ATIVO")
            print("=" * 70)
            print("Resolva o CAPTCHA manualmente no navegador.")
            print("O sistema está capturando todo o fluxo...")
            
            completed = await self._monitor_until_completion(page, timeout=120)
            
            # ============================================
            # CAPTURA FINAL E RELATÓRIO
            # ============================================
            await self._capture_form_snapshot(page, "final")
            await self._collect_worker_messages(page)
            await self._collect_dom_events(page)
            await self._generate_analysis_report(page)
            
            await browser.close()
            
            # Análise automática dos resultados
            self._print_analysis_summary()

    async def _setup_network_interceptors(self, page):
        """Configura interceptadores de rede com ID único"""
        
        async def handle_route(route, request):
            req_id = str(uuid.uuid4())[:12]
            
            # Determina se devemos armazenar body completo
            url_lower = request.url.lower()
            is_important = any(term in url_lower for term in [
                'captcha', 'pow', 'session', 'verify', 'challenge',
                'nonce', 'worker', 'filecrypt', 'cutcaptcha', 'validate'
            ])
            
            entry = {
                'id': req_id,
                'timestamp': datetime.now().isoformat(),
                'method': request.method,
                'url': request.url,
                'headers': dict(request.headers),
                'post_data': request.post_data,
                'resource_type': request.resource_type,
                'is_captcha_related': is_important,
                'response_body': None,
                'response_headers': None,
                'response_status': None
            }
            
            self.network_log.append(entry)
            self.request_map[req_id] = entry
            
            # Marca a request para associação posterior
            request._analysis_id = req_id
            
            await route.continue_()
        
        await page.route("**/*", handle_route)
        
        # Handler de response com associação direta
        async def handle_response(response):
            request = response.request
            req_id = getattr(request, '_analysis_id', None)
            
            if not req_id or req_id not in self.request_map:
                return
            
            entry = self.request_map[req_id]
            entry['response_status'] = response.status
            entry['response_headers'] = dict(response.headers)
            
            # Captura body apenas para tipos relevantes
            content_type = response.headers.get('content-type', '').lower()
            is_text = any(t in content_type for t in [
                'json', 'javascript', 'text', 'html', 'xml', 'wasm'
            ])
            
            if is_text or entry['is_captcha_related']:
                try:
                    body = await response.text()
                    entry['response_body'] = body
                    
                    # Se for session JSON, faz parse
                    if 'session' in entry['url'].lower() and 'json' in content_type:
                        try:
                            self.session_data = json.loads(body)
                            print(f"\n[SESSION] Dados da sessão capturados: {list(self.session_data.keys())}")
                        except:
                            self.session_data = {'raw': body[:1000]}
                            
                except:
                    entry['response_body'] = "[binary or unreadable]"
            
            # Se for relacionada ao CAPTCHA, adiciona à lista específica
            if entry['is_captcha_related']:
                self.captcha_requests.append(entry)
                print(f"\n[CAPTCHA REQUEST] {entry['method']} {entry['url'][:60]}...")
                if entry['post_data']:
                    print(f"  Body: {str(entry['post_data'])[:150]}")
        
        page.on("response", lambda res: asyncio.create_task(handle_response(res)))

    async def _setup_worker_interception(self, page):
        """Instrumenta Web Worker para capturar mensagens reais"""
        
        await page.add_init_script("""
            (() => {
                window._captchaWorkerMessages = [];
                window._workerUrls = [];
                
                const OriginalWorker = window.Worker;
                
                window.Worker = function(url, options) {
                    const workerUrl = url.toString();
                    window._workerUrls.push({
                        url: workerUrl,
                        timestamp: Date.now()
                    });
                    console.log('[Worker Created]', workerUrl);
                    
                    const worker = new OriginalWorker(url, options);
                    
                    // Intercepta mensagens PARA o worker
                    const originalPostMessage = worker.postMessage.bind(worker);
                    worker.postMessage = function(data, transfer) {
                        window._captchaWorkerMessages.push({
                            direction: 'to_worker',
                            worker_url: workerUrl,
                            data: JSON.parse(JSON.stringify(data)),
                            timestamp: Date.now()
                        });
                        console.log('[→ Worker]', data);
                        return originalPostMessage(data, transfer);
                    };
                    
                    // Intercepta mensagens DO worker
                    worker.addEventListener('message', (e) => {
                        window._captchaWorkerMessages.push({
                            direction: 'from_worker',
                            worker_url: workerUrl,
                            data: e.data,
                            timestamp: Date.now()
                        });
                        console.log('[← Worker]', e.data);
                    });
                    
                    return worker;
                };
                
                // Preserva prototype
                window.Worker.prototype = OriginalWorker.prototype;
            })();
        """)

    async def _setup_form_monitoring(self, page):
        """Monitora formulário, submit, fetch e XHR"""
        
        await page.add_init_script("""
            (() => {
                window._formEvents = [];
                
                // Monitora submit
                document.addEventListener('submit', (e) => {
                    const form = e.target;
                    const fields = {};
                    form.querySelectorAll('input, textarea, select').forEach(el => {
                        fields[el.name] = el.value;
                    });
                    
                    window._formEvents.push({
                        type: 'form_submit',
                        timestamp: Date.now(),
                        form_id: form.id,
                        form_action: form.action,
                        form_method: form.method,
                        fields: fields
                    });
                    console.log('[Form Submit]', form.action);
                }, true);
                
                // Monitora fetch
                const originalFetch = window.fetch;
                window.fetch = async function(...args) {
                    const url = args[0];
                    const options = args[1] || {};
                    
                    window._formEvents.push({
                        type: 'fetch',
                        timestamp: Date.now(),
                        url: url.toString(),
                        method: options.method || 'GET',
                        body: options.body
                    });
                    
                    return originalFetch.apply(this, args);
                };
                
                // Monitora XHR
                const OriginalXHR = XMLHttpRequest;
                window.XMLHttpRequest = function() {
                    const xhr = new OriginalXHR();
                    let requestInfo = {};
                    
                    const originalOpen = xhr.open;
                    xhr.open = function(method, url, ...rest) {
                        requestInfo = { method, url: url.toString() };
                        return originalOpen.apply(this, [method, url, ...rest]);
                    };
                    
                    const originalSend = xhr.send;
                    xhr.send = function(body) {
                        requestInfo.body = body;
                        requestInfo.timestamp = Date.now();
                        window._formEvents.push({
                            type: 'xhr',
                            ...requestInfo
                        });
                        return originalSend.apply(this, arguments);
                    };
                    
                    return xhr;
                };
            })();
        """)

    async def _setup_mutation_observer(self, page):
        """Observa mudanças no CAPTCHA e formulário"""
        
        await page.add_init_script("""
            (() => {
                window._captchaMutations = [];
                
                const observeCaptcha = () => {
                    const captchaDiv = document.getElementById('pow-captcha');
                    if (!captchaDiv) return;
                    
                    const observer = new MutationObserver((mutations) => {
                        mutations.forEach(mutation => {
                            if (mutation.type === 'attributes') {
                                window._captchaMutations.push({
                                    type: 'attribute_change',
                                    timestamp: Date.now(),
                                    attribute: mutation.attributeName,
                                    old_value: mutation.oldValue,
                                    new_value: captchaDiv.getAttribute(mutation.attributeName)
                                });
                            }
                        });
                    });
                    
                    observer.observe(captchaDiv, {
                        attributes: true,
                        attributeOldValue: true,
                        attributeFilter: ['data-state', 'data-session', 'class', 'style']
                    });
                };
                
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', observeCaptcha);
                } else {
                    observeCaptcha();
                }
            })();
        """)

    async def _extract_captcha_config(self, page):
        """Extrai configuração real do DOM"""
        
        config = await page.evaluate('''() => {
            const div = document.getElementById('pow-captcha');
            if (!div) return null;
            
            return {
                session: div.getAttribute('data-session'),
                worker: div.getAttribute('data-worker'),
                ext: div.getAttribute('data-ext'),
                sig: div.getAttribute('data-sig'),
                px: div.getAttribute('data-px'),
                state: div.getAttribute('data-state'),
                inner_text: div.innerText?.substring(0, 200) || '',
                pow_fields: Object.fromEntries(
                    [...document.querySelectorAll('#cform input[name^="pow_"]')]
                        .map(x => [x.name, x.value])
                )
            };
        }''')
        
        if config:
            print("\n[CONFIG] CAPTCHA detectado:")
            for k, v in config.items():
                if k not in ['pow_fields', 'inner_text']:
                    print(f"  data-{k}: {v}")
            
            print(f"\n[FIELDS] Campos pow_* encontrados: {list(config.get('pow_fields', {}).keys())}")
        
        return config

    async def _capture_form_snapshot(self, page, phase):
        """Captura snapshot dos campos pow_*"""
        
        snapshot = await page.evaluate('''() => {
            const fields = {};
            document.querySelectorAll('#cform input[name^="pow_"]').forEach(el => {
                fields[el.name] = {
                    value: el.value,
                    type: el.type,
                    id: el.id
                };
            });
            return {
                fields: fields,
                timestamp: Date.now(),
                captcha_state: document.getElementById('pow-captcha')?.getAttribute('data-state'),
                captcha_text: document.getElementById('pow-captcha')?.innerText?.substring(0, 100)
            };
        }''')
        
        entry = {
            'phase': phase,
            'timestamp': datetime.now().isoformat(),
            'data': snapshot
        }
        
        self.form_fields_log.append(entry)
        self._last_form_snapshot = snapshot
        
        print(f"\n[FORM {phase.upper()}]")
        for name, info in snapshot.get('fields', {}).items():
            val = info.get('value', '')
            display = val[:50] + '...' if len(str(val)) > 50 else val
            print(f"  {name}: {display or '(vazio)'}")

    async def _download_scripts(self, page):
        """Baixa e preserva scripts completos"""
        
        print("\n[SCRIPTS] Baixando arquivos JavaScript...")
        
        base_url = "https://filecrypt.cc"
        scripts_to_fetch = [
            ('worker', self.captcha_config.get('worker')),
            ('ext', self.captcha_config.get('ext')),
            ('sig', self.captcha_config.get('sig')),
            ('main', '/js/pow_captcha.js')
        ]
        
        for name, url in scripts_to_fetch:
            if not url:
                continue
            
            # Resolve URL relativa
            if url.startswith('/'):
                full_url = base_url + url
            elif url.startswith('http'):
                full_url = url
            else:
                full_url = base_url + '/' + url
            
            try:
                # Usa fetch no navegador para manter cookies
                content = await page.evaluate(f'''async () => {{
                    try {{
                        const r = await fetch("{full_url}");
                        return await r.text();
                    }} catch(e) {{
                        return "ERROR: " + e.message;
                    }}
                }}''')
                
                if content.startswith("ERROR:"):
                    print(f"  ✗ {name}: {content}")
                    continue
                
                self.scripts[name] = content
                self.scripts_content[name] = content  # Preservação completa
                
                filename = f'filecrypt_{name}.js'
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"  ✓ {name}: {len(content)} bytes → {filename}")
                
                # Análise complementar por regex
                self._analyze_script_content(name, content)
                
            except Exception as e:
                print(f"  ✗ {name}: {e}")

    def _analyze_script_content(self, name, content):
        """Análise regex complementar"""
        
        patterns = {
            'Worker': r'new\s+Worker\s*\(\s*["\']([^"\']+)["\']',
            'postMessage': r'postMessage\s*\(([^)]+)\)',
            'onmessage': r'onmessage\s*[=:]\s*function\s*\(([^)]*)\)',
            'fetch': r'fetch\s*\(\s*["\']([^"\']+)["\']',
            'XMLHttpRequest': r'new\s+XMLHttpRequest',
            'crypto.subtle': r'crypto\.subtle',
            'digest': r'\.digest\s*\(',
            'FormData': r'new\s+FormData',
            'URLSearchParams': r'new\s+URLSearchParams',
            'nonce': r'nonce',
            'challenge': r'challenge',
            'session': r'session',
            'pow_': r'pow_[a-z_]+',
            'submit': r'\.submit\s*\('
        }
        
        print(f"\n    [Análise {name}.js]:")
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                print(f"      • {pattern_name}: {len(matches)} ocorrências")

    async def _monitor_until_completion(self, page, timeout=120):
        """Monitora até detectar conclusão, sem depender só de data-state"""
        
        start_time = time.time()
        last_fields_hash = None
        check_count = 0
        
        print(f"\n[MONITOR] Aguardando resolução (timeout: {timeout}s)...")
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # Verifica múltiplos sinais de conclusão
            completion_checks = await page.evaluate('''() => {
                const captchaDiv = document.getElementById('pow-captcha');
                const results = {
                    data_state: captchaDiv?.getAttribute('data-state'),
                    captcha_text: captchaDiv?.innerText || '',
                    form_exists: !!document.getElementById('cform'),
                    pow_fields: {},
                    links_visible: document.querySelectorAll('a[href*="filecrypt"]').length > 5
                };
                
                // Captura todos os campos pow_
                document.querySelectorAll('input[name^="pow_"]').forEach(el => {
                    results.pow_fields[el.name] = el.value;
                });
                
                return results;
            }''')
            
            current_fields = json.dumps(completion_checks.get('pow_fields', {}), sort_keys=True)
            state = completion_checks.get('data_state')
            
            # Detecta mudanças nos campos
            if current_fields != last_fields_hash:
                if last_fields_hash is not None:
                    print(f"\n  [CHANGE] Campos pow_* alterados!")
                    await self._capture_form_snapshot(page, f"change_{check_count}")
                last_fields_hash = current_fields
            
            # Sinais de conclusão
            is_done = (
                state in ['done', 'completed', 'success'] or
                completion_checks.get('links_visible') or
                'solved' in completion_checks.get('captcha_text', '').lower()
            )
            
            if is_done:
                print(f"\n[✓] CAPTCHA concluído detectado!")
                print(f"    Estado: {state}")
                print(f"    Links visíveis: {completion_checks.get('links_visible')}")
                self._captcha_completed = True
                self.completion_signals.append({
                    'type': 'captcha_done',
                    'timestamp': datetime.now().isoformat(),
                    'state': state,
                    'checks': completion_checks
                })
                return True
            
            # Log a cada 5 segundos
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0 and elapsed > 0:
                print(f"  [{elapsed}s] Estado: {state or 'n/a'} | Campos: {len(completion_checks.get('pow_fields', {}))}")
            
            await asyncio.sleep(0.5)
        
        print(f"\n[!] Timeout após {timeout}s")
        return False

    async def _collect_worker_messages(self, page):
        """Coleta mensagens do worker do contexto da página"""
        
        messages = await page.evaluate('''() => {
            return window._captchaWorkerMessages || [];
        }''')
        
        self.worker_messages = messages
        print(f"\n[WORKER] {len(messages)} mensagens capturadas")
        
        for msg in messages[-5:]:  # Mostra últimas 5
            direction = "→" if msg.get('direction') == 'to_worker' else "←"
            print(f"  {direction} {str(msg.get('data', ''))[:80]}")

    async def _collect_dom_events(self, page):
        """Coleta eventos do DOM"""
        
        events = await page.evaluate('''() => {
            return {
                form_events: window._formEvents || [],
                mutations: window._captchaMutations || [],
                worker_urls: window._workerUrls || []
            };
        }''')
        
        self.dom_events = events.get('mutations', [])
        self.validation_events = events.get('form_events', [])
        
        print(f"\n[DOM] {len(self.dom_events)} mutações capturadas")
        print(f"[FORM] {len(self.validation_events)} eventos de formulário")

    async def _generate_analysis_report(self, page):
        """Gera relatório JSON completo"""
        
        # Detecta eventos de validação
        validation_requests = [
            r for r in self.captcha_requests
            if r.get('method') == 'POST' or 'verify' in r.get('url', '').lower()
        ]
        
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'container_url': page.url,
            
            'captcha_config': self.captcha_config,
            
            'session': self.session_data,
            
            'scripts_analyzed': {
                name: {
                    'filename': f'filecrypt_{name}.js',
                    'size_bytes': len(content),
                    'saved': os.path.exists(f'filecrypt_{name}.js')
                }
                for name, content in self.scripts.items()
            },
            
            'network_summary': {
                'total_requests': len(self.network_log),
                'captcha_related_requests': len(self.captcha_requests),
                'validation_candidates': len(validation_requests)
            },
            
            'captcha_requests': [
                {
                    'id': r['id'],
                    'timestamp': r['timestamp'],
                    'method': r['method'],
                    'url': r['url'],
                    'status': r.get('response_status'),
                    'is_captcha_marked': r.get('is_captcha_related'),
                    'post_data': r.get('post_data'),
                    'response_preview': (
                        (r.get('response_body', '')[:300] + '...') 
                        if r.get('response_body') else None
                    )
                }
                for r in self.captcha_requests
            ],
            
            'form_evolution': self.form_fields_log,
            
            'worker_messages': self.worker_messages,
            
            'dom_events': self.dom_events[-20:] if len(self.dom_events) > 20 else self.dom_events,
            
            'validation_events': self.validation_events,
            
            'completion_signals': self.completion_signals,
            
            'validation_candidates': [
                {
                    'method': r['method'],
                    'url': r['url'],
                    'status': r.get('response_status'),
                    'has_body': r.get('post_data') is not None
                }
                for r in validation_requests[-3:]
            ]
        }
        
        # Salva relatório
        filename = 'filecrypt_analysis_report.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n[REPORT] Relatório salvo: {filename}")
        return report

    def _print_analysis_summary(self):
        """Análise automática dos resultados capturados"""
        
        print("\n" + "=" * 70)
        print("ANÁLISE DOS RESULTADOS")
        print("=" * 70)
        
        # Session endpoint
        if self.session_data:
            print("[+] Session endpoint encontrado")
            print(f"    Campos: {list(self.session_data.keys())}")
        else:
            print("[-] Session endpoint não encontrado")
        
        # Worker
        worker_msgs = [m for m in self.worker_messages if m.get('direction') == 'to_worker']
        if worker_msgs:
            print("[+] Worker encontrado")
            print(f"    Mensagens para worker: {len(worker_msgs)}")
        else:
            print("[-] Worker não instrumentado ou não utilizado")
        
        # Worker input/output
        to_worker = [m for m in self.worker_messages if m.get('direction') == 'to_worker']
        from_worker = [m for m in self.worker_messages if m.get('direction') == 'from_worker']
        
        if to_worker:
            print("[+] Worker input observado")
        else:
            print("[-] Worker input não observado")
            
        if from_worker:
            print("[+] Worker output observado")
        else:
            print("[-] Worker output não observado")
        
        # Campos pow_*
        if len(self.form_fields_log) > 1:
            print("[+] Campos pow_* alterados durante execução")
            print(f"    Snapshots: {len(self.form_fields_log)}")
        else:
            print("[-] Campos pow_* não mostraram evolução")
        
        # Request de validação
        validation_posts = [
            r for r in self.captcha_requests 
            if r.get('method') == 'POST' and r.get('response_status') in [200, 201, 204]
        ]
        if validation_posts:
            print("[+] Request de validação encontrado")
            for r in validation_posts[:2]:
                print(f"    {r['method']} {r['url'][:50]}...")
        else:
            print("[-] Request de validação não identificado")
        
        # Resposta de validação
        if validation_posts and any(r.get('response_body') for r in validation_posts):
            print("[+] Resposta de validação capturada")
        else:
            print("[-] Resposta de validação não capturada")
        
        # Sinal de conclusão
        if self._captcha_completed:
            print("[+] Sinal de CAPTCHA concluído detectado")
        else:
            print("[-] CAPTCHA não foi concluído no tempo limite")
        
        print("\n" + "=" * 70)
        print("ARQUIVOS GERADOS:")
        print("  - filecrypt_analysis_report.json")
        print("  - filecrypt_worker.js (se worker existir)")
        print("  - filecrypt_ext.js (se ext existir)")
        print("  - filecrypt_sig.js (se sig existir)")
        print("  - filecrypt_main.js")
        print("=" * 70)


# ============================================
# EXECUÇÃO
# ============================================
if __name__ == "__main__":
    analyzer = FileCryptAnalyzer()
    
    # URL do container - altere conforme necessário
    CONTAINER_URL = "https://filecrypt.cc/Container/6912073BCA.html"
    
    try:
        asyncio.run(analyzer.run_analysis(CONTAINER_URL))
    except KeyboardInterrupt:
        print("\n\n[!] Análise interrompida pelo usuário")
    except Exception as e:
        print(f"\n\n[✗] Erro: {e}")
        import traceback
        traceback.print_exc()