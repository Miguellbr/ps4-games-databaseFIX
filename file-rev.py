#!/usr/bin/env python3
"""
FileCrypt Reverse Engineering Tool - file-rev.py
Ferramenta automatizada de processamento do fluxo de verificação do FileCrypt.

Arquitetura: URL → DESCOBERTA → DESAFIO → SESSÃO → PROCESSAMENTO → ENVIO → VALIDAÇÃO → RESULTADO
"""

import asyncio
import json
import uuid
import time
import hashlib
import base64
import re
import os
import sys
import argparse
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum, auto
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Request, Response


class ChallengeState(Enum):
    """Estados da máquina de estados do desafio"""
    INIT = "INIT"
    CHALLENGE_DISCOVERY = "CHALLENGE_DISCOVERY"
    CHALLENGE_ACQUIRED = "CHALLENGE_ACQUIRED"
    PROCESSING = "PROCESSING"
    RESULT_READY = "RESULT_READY"
    SUBMISSION = "SUBMISSION"
    SERVER_VALIDATION = "SERVER_VALIDATION"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class Challenge:
    """Modelo interno do desafio"""
    challenge_id: Optional[str] = None
    session_id: Optional[str] = None
    payload: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    client_state: Dict[str, Any] = field(default_factory=dict)
    processing_state: Dict[str, Any] = field(default_factory=dict)
    processing_result: Optional[str] = None
    submission_state: Dict[str, Any] = field(default_factory=dict)
    validation_state: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SessionContext:
    """Contexto isolado da sessão"""
    session_id: Optional[str] = None
    cookies: List[Dict] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    identifiers: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    dom_state: Dict[str, Any] = field(default_factory=dict)
    responses: List[Dict] = field(default_factory=list)
    challenge_info: Optional[Challenge] = None
    modifications: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        if self.challenge_info:
            result['challenge_info'] = self.challenge_info.to_dict()
        return result


@dataclass
class ScriptInfo:
    """Informações sobre scripts descobertos"""
    url: str
    name: str
    size: int = 0
    sha256: Optional[str] = None
    timestamp: Optional[str] = None
    content: Optional[str] = None
    script_type: str = "UNKNOWN"  # CAPTCHA, WORKER, EXTENSION, SIGNATURE, SESSION, VALIDATION, OTHER
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class WorkerMessage:
    """Mensagem de/para Worker"""
    timestamp: str
    direction: str  # 'to_worker' ou 'from_worker'
    worker_url: Optional[str] = None
    message_type: Optional[str] = None
    size: int = 0
    content: Any = None
    correlation_id: Optional[str] = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NetworkRequest:
    """Request de rede capturado"""
    request_id: str
    timestamp: str
    method: str
    url: str
    resource_type: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    classification: str = "OTHER"  # SCRIPT, WORKER, SESSION, CHALLENGE, PROCESSING, SUBMISSION, VALIDATION_CANDIDATE
    related_challenge: Optional[str] = None
    related_session: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NetworkResponse:
    """Response de rede capturado"""
    request_id: str
    timestamp: str
    status: int
    url: str
    content_type: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    size: int = 0
    body: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EventTraceEntry:
    """Entrada do trace cronológico"""
    timestamp: str
    event_type: str
    source: str
    challenge_id: Optional[str] = None
    session_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StateTransition:
    """Transição de estado"""
    from_state: ChallengeState
    to_state: ChallengeState
    timestamp: str
    reason: Optional[str] = None
    evidence: Optional[str] = None
    related_request: Optional[str] = None
    related_response: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'from_state': self.from_state.value,
            'to_state': self.to_state.value,
            'timestamp': self.timestamp,
            'reason': self.reason,
            'evidence': self.evidence,
            'related_request': self.related_request,
            'related_response': self.related_response
        }


class FileCryptAnalyzer:
    """
    Analisador forense completo do FileCrypt CAPTCHA.
    ZERO suposições - apenas dados observados.
    """
    
    def __init__(self):
        # Estruturas de dados principais
        self.scripts: Dict[str, ScriptInfo] = {}
        self.network_requests: Dict[str, NetworkRequest] = {}
        self.network_responses: Dict[str, NetworkResponse] = {}
        self.worker_messages: List[WorkerMessage] = []
        self.worker_message_pairs: List[Tuple[str, str]] = []  # (input_id, output_id)
        self.event_trace: List[EventTraceEntry] = []
        self.state_transitions: List[StateTransition] = []
        
        # Contextos
        self.current_challenge: Optional[Challenge] = None
        self.current_session: Optional[SessionContext] = None
        
        # Estado
        self.current_state: ChallengeState = ChallengeState.INIT
        self.scripts_discovered: List[str] = []
        self.pow_fields_history: List[Dict] = []
        self.validation_candidates: List[Dict] = []
        self.errors: List[Dict] = []
        self.unknowns: List[str] = []
        
        # Dados de processamento
        self.server_input: Dict[str, Any] = {}
        self.client_state: Dict[str, Any] = {}
        self.processing_data: Dict[str, Any] = {}
        self.processing_result: Optional[str] = None
        self.server_validation: Dict[str, Any] = {}
        
        # Elementos DOM
        self.captcha_element_data: Dict[str, Any] = {}
        self.form_fields_log: List[Dict] = []
        self.dom_mutations: List[Dict] = []
        
        # Resultado final
        self.final_result: Optional[Dict] = None
        
    def _trace(self, event_type: str, data: Dict[str, Any], source: str = "analyzer"):
        """Registra evento no trace cronológico"""
        entry = EventTraceEntry(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            source=source,
            challenge_id=self.current_challenge.challenge_id if self.current_challenge else None,
            session_id=self.current_session.session_id if self.current_session else None,
            data=data
        )
        self.event_trace.append(entry)
        print(f"[TRACE:{event_type}] {str(data)[:120]}")
        
    def _transition_state(self, new_state: ChallengeState, reason: Optional[str] = None,
                         evidence: Optional[str] = None, request_id: Optional[str] = None,
                         response_id: Optional[str] = None):
        """Transiciona a máquina de estados"""
        old_state = self.current_state
        self.current_state = new_state
        
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now().isoformat(),
            reason=reason,
            evidence=evidence,
            related_request=request_id,
            related_response=response_id
        )
        self.state_transitions.append(transition)
        
        self._trace("state_transition", {
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "evidence": evidence
        })
        
    def _log_error(self, context: str, error: Exception, evidence: Optional[str] = None):
        """Registra erro de forma robusta"""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "evidence": evidence,
            "current_state": self.current_state.value
        }
        self.errors.append(error_entry)
        self._trace("error", error_entry)
        
    def _log_unknown(self, description: str):
        """Registra algo que não pôde ser determinado"""
        self.unknowns.append({
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "current_state": self.current_state.value
        })
        self._trace("unknown", {"description": description})
        
    def _classify_request(self, request: Request) -> str:
        """Classifica request baseado em evidências"""
        url = request.url.lower()
        resource_type = request.resource_type
        
        # Verifica padrões de URL
        if 'worker' in url or 'worker' in resource_type:
            return "WORKER"
        if any(x in url for x in ['captcha', 'challenge', 'pow']):
            return "CHALLENGE"
        if any(x in url for x in ['session', 'sess']):
            return "SESSION"
        if any(x in url for x in ['validate', 'verify', 'check', 'submit']):
            return "VALIDATION_CANDIDATE"
        if resource_type in ['script', 'javascript']:
            return "SCRIPT"
        if 'process' in url or 'process' in resource_type:
            return "PROCESSING"
            
        return "OTHER"
        
    def _compute_sha256(self, content: str) -> str:
        """Calcula SHA-256 do conteúdo"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
        
    async def _discover_challenge(self, page: Page):
        """Descobre automaticamente o desafio ao abrir a URL"""
        self._transition_state(ChallengeState.CHALLENGE_DISCOVERY, 
                              reason="Iniciando descoberta do desafio")
        
        try:
            # Aguarda carregamento básico
            await page.wait_for_load_state('networkidle')
            
            # Procura pelo componente #pow-captcha
            captcha_exists = await page.evaluate('''() => {
                const el = document.getElementById('pow-captcha');
                return el !== null;
            }''')
            
            if not captcha_exists:
                self._log_unknown("Elemento #pow-captcha não encontrado")
                return False
                
            # Extrai todos os atributos data-* do captcha
            captcha_data = await page.evaluate('''() => {
                const el = document.getElementById('pow-captcha');
                if (!el) return null;
                
                const data = {};
                for (const attr of el.attributes) {
                    if (attr.name.startsWith('data-')) {
                        data[attr.name] = attr.value;
                    }
                }
                return data;
            }''')
            
            self.captcha_element_data = captcha_data or {}
            
            # Extrai campos pow_*
            pow_fields = await page.evaluate('''() => {
                const fields = {};
                const elements = document.querySelectorAll('[id^="pow_"], [name^="pow_"]');
                elements.forEach(el => {
                    const key = el.id || el.name;
                    fields[key] = {
                        value: el.value || null,
                        type: el.type || el.tagName.toLowerCase(),
                        attributes: {}
                    };
                    for (const attr of el.attributes) {
                        fields[key].attributes[attr.name] = attr.value;
                    }
                });
                return fields;
            }''')
            
            # Cria o desafio
            self.current_challenge = Challenge(
                challenge_id=captcha_data.get('data-session') if captcha_data else None,
                session_id=captcha_data.get('data-session') if captcha_data else None,
                payload=json.dumps(captcha_data) if captcha_data else None,
                parameters={
                    'data_worker': captcha_data.get('data-worker'),
                    'data_ext': captcha_data.get('data-ext'),
                    'data_sig': captcha_data.get('data-sig'),
                    'data_px': captcha_data.get('data-px'),
                    'data_state': captcha_data.get('data-state'),
                    'pow_fields': pow_fields
                },
                source="DOM#pow-captcha",
                created_at=datetime.now().isoformat()
            )
            
            # Registra estado inicial do cliente
            self.client_state = {
                'captcha_attributes': captcha_data,
                'pow_fields_initial': pow_fields,
                'timestamp': datetime.now().isoformat()
            }
            
            self._transition_state(ChallengeState.CHALLENGE_ACQUIRED,
                                  reason="Desafio identificado no DOM",
                                  evidence=json.dumps(captcha_data))
            
            self._trace("challenge_discovered", {
                "challenge_id": self.current_challenge.challenge_id,
                "attributes": captcha_data,
                "pow_fields": pow_fields
            })
            
            return True
            
        except Exception as e:
            self._log_error("discover_challenge", e)
            self._transition_state(ChallengeState.ERROR, reason=str(e))
            return False
            
    async def _instrument_workers(self, page: Page):
        """Instrumenta a criação e comunicação dos Workers"""
        
        # Intercepta criação de Workers
        await page.evaluate('''() => {
            const originalWorker = window.Worker;
            window.Worker = function(url) {
                const worker = new originalWorker(url);
                window._workerUrl = url;
                
                // Intercepta postMessage
                const originalPostMessage = worker.postMessage.bind(worker);
                worker.postMessage = function(message) {
                    if (window._workerMessages) {
                        window._workerMessages.push({
                            direction: 'to_worker',
                            url: window._workerUrl,
                            message: message,
                            timestamp: new Date().toISOString()
                        });
                    }
                    return originalPostMessage(message);
                };
                
                // Intercepta onmessage
                worker.addEventListener('message', (event) => {
                    if (window._workerMessages) {
                        window._workerMessages.push({
                            direction: 'from_worker',
                            url: window._workerUrl,
                            message: event.data,
                            timestamp: new Date().toISOString()
                        });
                    }
                });
                
                return worker;
            };
            
            window._workerMessages = [];
        }''')
        
        self._trace("worker_instrumentation", {"status": "enabled"})
        
    async def _collect_worker_messages(self, page: Page):
        """Coleta mensagens do Worker"""
        try:
            messages = await page.evaluate('() => window._workerMessages || []')
            
            for msg in messages:
                worker_msg = WorkerMessage(
                    timestamp=msg.get('timestamp', datetime.now().isoformat()),
                    direction=msg.get('direction', 'unknown'),
                    worker_url=msg.get('url'),
                    content=msg.get('message'),
                    size=len(json.dumps(msg.get('message'))) if msg.get('message') else 0
                )
                self.worker_messages.append(worker_msg)
                
                self._trace(f"worker_{msg.get('direction', 'unknown')}", {
                    "url": msg.get('url'),
                    "content": msg.get('message')
                })
                
        except Exception as e:
            self._log_error("collect_worker_messages", e)
            
    async def _monitor_dom_changes(self, page: Page):
        """Monitora alterações no DOM relacionadas ao desafio"""
        
        # Configura MutationObserver
        await page.evaluate('''() => {
            if (window._domObserver) return;
            
            window._domMutations = [];
            
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    const record = {
                        timestamp: new Date().toISOString(),
                        type: mutation.type,
                        target: mutation.target.id || mutation.target.name || mutation.target.tagName,
                        attributeName: mutation.attributeName,
                        oldValue: mutation.oldValue
                    };
                    
                    // Captura valores atuais de campos pow_*
                    if (mutation.target.id && mutation.target.id.startsWith('pow_')) {
                        record.newValue = mutation.target.value;
                    }
                    
                    window._domMutations.push(record);
                });
            });
            
            observer.observe(document.body, {
                attributes: true,
                attributeOldValue: true,
                childList: true,
                subtree: true
            });
            
            window._domObserver = observer;
        }''')
        
        self._trace("dom_monitoring", {"status": "enabled"})
        
    async def _collect_dom_mutations(self, page: Page):
        """Coleta mutações do DOM"""
        try:
            mutations = await page.evaluate('() => window._domMutations || []')
            self.dom_mutations.extend(mutations)
            
            for mutation in mutations:
                if mutation.get('attributeName') and mutation['attributeName'].startswith('data-'):
                    self._trace("dom_mutation", mutation)
                    
        except Exception as e:
            self._log_error("collect_dom_mutations", e)
            
    async def _capture_network(self, page: Page):
        """Configura captura de rede"""
        
        def handle_request(request: Request):
            try:
                classification = self._classify_request(request)
                
                req = NetworkRequest(
                    request_id=request.url + '_' + str(time.time()),
                    timestamp=datetime.now().isoformat(),
                    method=request.method,
                    url=request.url,
                    resource_type=request.resource_type,
                    headers=dict(request.headers),
                    classification=classification,
                    related_challenge=self.current_challenge.challenge_id if self.current_challenge else None,
                    related_session=self.current_session.session_id if self.current_session else None
                )
                
                # Tenta obter body
                try:
                    post_data = request.post_data
                    if post_data:
                        req.body = post_data[:10000] if len(post_data) > 10000 else post_data
                except:
                    pass
                    
                self.network_requests[req.request_id] = req
                
                self._trace("request", {
                    "method": req.method,
                    "url": req.url,
                    "classification": classification
                })
                
            except Exception as e:
                self._log_error("handle_request", e)
                
        def handle_response(response: Response):
            try:
                request_id = response.request.url + '_' + str(time.time())
                
                resp = NetworkResponse(
                    request_id=request_id,
                    timestamp=datetime.now().isoformat(),
                    status=response.status,
                    url=response.url,
                    content_type=response.headers.get('content-type'),
                    headers=dict(response.headers),
                    size=0
                )
                
                self.network_responses[request_id] = resp
                
                self._trace("response", {
                    "status": resp.status,
                    "url": resp.url,
                    "content_type": resp.content_type
                })
                
            except Exception as e:
                self._log_error("handle_response", e)
                
        page.on("request", handle_request)
        page.on("response", handle_response)
        
    async def _discover_scripts(self, page: Page):
        """Descobre URLs reais dos scripts"""
        
        try:
            # Coleta todos os scripts da página
            scripts_info = await page.evaluate('''() => {
                const scripts = [];
                document.querySelectorAll('script').forEach((script, index) => {
                    scripts.push({
                        index: index,
                        src: script.src,
                        type: script.type,
                        async: script.async,
                        defer: script.defer,
                        content_length: script.textContent ? script.textContent.length : 0
                    });
                });
                return scripts;
            }''')
            
            for script_info in scripts_info:
                url = script_info.get('src')
                if url:
                    # Determina tipo do script baseado em evidências
                    script_type = "OTHER"
                    if 'worker' in url.lower():
                        script_type = "WORKER"
                    elif any(x in url.lower() for x in ['captcha', 'pow', 'challenge']):
                        script_type = "CAPTCHA"
                    elif 'ext' in url.lower():
                        script_type = "EXTENSION"
                    elif 'sig' in url.lower():
                        script_type = "SIGNATURE"
                    elif 'session' in url.lower():
                        script_type = "SESSION"
                        
                    self.scripts[url] = ScriptInfo(
                        url=url,
                        name=url.split('/')[-1] if '/' in url else url,
                        script_type=script_type,
                        timestamp=datetime.now().isoformat()
                    )
                    
                    self._trace("script_discovered", {
                        "url": url,
                        "type": script_type
                    })
                    
        except Exception as e:
            self._log_error("discover_scripts", e)
            
    async def _wait_for_processing(self, page: Page, timeout: int = 60):
        """Aguarda processamento do desafio"""
        self._transition_state(ChallengeState.PROCESSING,
                              reason="Aguardando processamento do desafio")
        
        start_time = time.time()
        last_pow_hash = None
        
        while time.time() - start_time < timeout:
            try:
                # Verifica campos pow_* para mudanças
                current_pow = await page.evaluate('''() => {
                    const fields = {};
                    document.querySelectorAll('[id^="pow_"], [name^="pow_"]').forEach(el => {
                        const key = el.id || el.name;
                        fields[key] = el.value;
                    });
                    return fields;
                }''')
                
                # Detecta mudanças
                if current_pow != last_pow_hash:
                    self.pow_fields_history.append({
                        "timestamp": datetime.now().isoformat(),
                        "fields": current_pow
                    })
                    last_pow_hash = current_pow
                    
                # Verifica se há resultado
                has_result = await page.evaluate('''() => {
                    // Procura por campos preenchidos ou sinais de conclusão
                    const fields = document.querySelectorAll('[id^="pow_"]');
                    for (const f of fields) {
                        if (f.value && f.value.length > 10) return true;
                    }
                    return false;
                }''')
                
                if has_result:
                    self.processing_result = json.dumps(current_pow)
                    self._transition_state(ChallengeState.RESULT_READY,
                                          reason="Resultado de processamento detectado",
                                          evidence=json.dumps(current_pow))
                    return True
                    
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self._log_error("wait_for_processing", e)
                await asyncio.sleep(0.5)
                
        self._log_unknown("Timeout aguardando processamento")
        return False
        
    async def _identify_submission(self, page: Page):
        """Identifica etapa de submissão"""
        self._transition_state(ChallengeState.SUBMISSION,
                              reason="Identificando submissão")
        
        try:
            # Procura por forms ou botões de submit
            submission_elements = await page.evaluate('''() => {
                const elements = [];
                
                // Forms
                document.querySelectorAll('form').forEach((form, i) => {
                    elements.push({
                        type: 'form',
                        index: i,
                        action: form.action,
                        method: form.method,
                        id: form.id,
                        class: form.className
                    });
                });
                
                // Botões de submit
                document.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((btn, i) => {
                    elements.push({
                        type: 'submit_button',
                        index: i,
                        id: btn.id,
                        name: btn.name,
                        value: btn.value
                    });
                });
                
                return elements;
            }''')
            
            self.current_challenge.submission_state = {
                "elements": submission_elements,
                "timestamp": datetime.now().isoformat()
            }
            
            self._trace("submission_identified", {
                "elements_count": len(submission_elements)
            })
            
        except Exception as e:
            self._log_error("identify_submission", e)
            
    async def _validate_with_server(self, page: Page):
        """Valida resultado com o servidor"""
        self._transition_state(ChallengeState.SERVER_VALIDATION,
                              reason="Validando com servidor")
        
        try:
            # Aguarda requests de validação
            await asyncio.sleep(2)
            
            # Analisa requests de validação candidatos
            validation_requests = [r for r in self.network_requests.values() 
                                  if r.classification == "VALIDATION_CANDIDATE"]
            
            if validation_requests:
                for req in validation_requests:
                    # Procura response correspondente
                    resp = self.network_responses.get(req.request_id)
                    
                    if resp:
                        # Analisa resposta
                        is_accepted = False
                        evidence = {}
                        
                        if resp.status == 200:
                            is_accepted = True
                            evidence["status"] = 200
                            
                        self.current_challenge.validation_state = {
                            "request": req.to_dict(),
                            "response": resp.to_dict() if resp else None,
                            "result": "ACCEPTED" if is_accepted else "REJECTED",
                            "evidence": evidence,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        if is_accepted:
                            self._transition_state(ChallengeState.ACCEPTED,
                                                  reason="Servidor respondeu 200",
                                                  evidence=str(resp.status))
                        else:
                            self._transition_state(ChallengeState.REJECTED,
                                                  reason=f"Status: {resp.status}",
                                                  evidence=str(resp.status))
                        return
                        
            # Se não encontrou validação clara
            self._transition_state(ChallengeState.UNKNOWN,
                                  reason="Não foi possível determinar validação do servidor")
                                  
        except Exception as e:
            self._log_error("validate_with_server", e)
            self._transition_state(ChallengeState.ERROR, reason=str(e))
            
    def _build_final_result(self) -> Dict:
        """Constrói objeto final estruturado"""
        
        result = {
            "challenge": self.current_challenge.to_dict() if self.current_challenge else None,
            "session": self.current_session.to_dict() if self.current_session else None,
            "processing": {
                "server_input": self.server_input,
                "client_state": self.client_state,
                "processing_data": self.processing_data,
                "processing_result": self.processing_result
            },
            "submission": self.current_challenge.submission_state if self.current_challenge else {},
            "validation": self.current_challenge.validation_state if self.current_challenge else {},
            "final_state": {
                "current_state": self.current_state.value,
                "transitions": [t.to_dict() for t in self.state_transitions]
            },
            "evidence": {
                "scripts": {k: v.to_dict() for k, v in self.scripts.items()},
                "network_requests": {k: v.to_dict() for k, v in self.network_requests.items()},
                "network_responses": {k: v.to_dict() for k, v in self.network_responses.items()},
                "worker_messages": [m.to_dict() for m in self.worker_messages],
                "dom_mutations": self.dom_mutations,
                "pow_fields_history": self.pow_fields_history
            },
            "errors": self.errors,
            "unknowns": self.unknowns,
            "event_trace": [e.to_dict() for e in self.event_trace]
        }
        
        self.final_result = result
        return result
        
    def _generate_text_report(self) -> str:
        """Gera relatório em formato TXT"""
        
        lines = []
        lines.append("=" * 80)
        lines.append("FILECRYPT FLOW ANALYSIS REPORT")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("=" * 80)
        lines.append("")
        
        # 1. Configuração
        lines.append("1. CONFIGURAÇÃO")
        lines.append("-" * 40)
        lines.append(f"Estado Final: {self.current_state.value}")
        lines.append(f"Total de Transições: {len(self.state_transitions)}")
        lines.append("")
        
        # 2. Desafio
        lines.append("2. DESAFIO")
        lines.append("-" * 40)
        if self.current_challenge:
            lines.append(f"Challenge ID: {self.current_challenge.challenge_id or 'UNKNOWN'}")
            lines.append(f"Session ID: {self.current_challenge.session_id or 'UNKNOWN'}")
            lines.append(f"Source: {self.current_challenge.source or 'UNKNOWN'}")
            lines.append(f"Created At: {self.current_challenge.created_at or 'UNKNOWN'}")
            lines.append(f"Parameters: {json.dumps(self.current_challenge.parameters, indent=2)}")
        else:
            lines.append("Desafio não identificado")
        lines.append("")
        
        # 3. Sessão
        lines.append("3. SESSÃO")
        lines.append("-" * 40)
        if self.current_session:
            lines.append(f"Session ID: {self.current_session.session_id or 'UNKNOWN'}")
            lines.append(f"Cookies: {len(self.current_session.cookies)}")
            lines.append(f"Headers: {json.dumps(self.current_session.headers, indent=2)}")
        else:
            lines.append("Sessão não estabelecida")
        lines.append("")
        
        # 4. Scripts
        lines.append("4. SCRIPTS")
        lines.append("-" * 40)
        for url, script in self.scripts.items():
            lines.append(f"  - {script.name}")
            lines.append(f"    URL: {url}")
            lines.append(f"    Type: {script.script_type}")
            lines.append(f"    Size: {script.size}")
            lines.append(f"    SHA-256: {script.sha256 or 'N/A'}")
            lines.append("")
            
        # 5. Worker
        lines.append("5. WORKER")
        lines.append("-" * 40)
        lines.append(f"Total Mensagens: {len(self.worker_messages)}")
        for msg in self.worker_messages[:10]:  # Primeiras 10
            lines.append(f"  [{msg.direction}] {msg.timestamp}")
            lines.append(f"    Type: {msg.message_type or 'N/A'}")
            lines.append(f"    Size: {msg.size}")
            lines.append("")
            
        # 6. Entradas
        lines.append("6. ENTRADAS")
        lines.append("-" * 40)
        lines.append(f"Server Input: {json.dumps(self.server_input, indent=2)}")
        lines.append(f"Client State: {json.dumps(self.client_state, indent=2)}")
        lines.append("")
        
        # 7. Saídas
        lines.append("7. SAÍDAS")
        lines.append("-" * 40)
        lines.append(f"Processing Result: {self.processing_result or 'UNKNOWN'}")
        lines.append("")
        
        # 8. Campos pow_*
        lines.append("8. CAMPOS POW_*")
        lines.append("-" * 40)
        for entry in self.pow_fields_history:
            lines.append(f"  [{entry['timestamp']}]")
            for field, value in entry['fields'].items():
                lines.append(f"    {field}: {value}")
            lines.append("")
            
        # 9. Requests
        lines.append("9. REQUESTS")
        lines.append("-" * 40)
        for req_id, req in self.network_requests.items():
            lines.append(f"  [{req.method}] {req.url[:80]}")
            lines.append(f"    Classification: {req.classification}")
            lines.append(f"    Resource Type: {req.resource_type}")
            lines.append("")
            
        # 10. Responses
        lines.append("10. RESPONSES")
        lines.append("-" * 40)
        for resp_id, resp in self.network_responses.items():
            lines.append(f"  [{resp.status}] {resp.url[:80]}")
            lines.append(f"    Content-Type: {resp.content_type or 'N/A'}")
            lines.append(f"    Size: {resp.size}")
            lines.append("")
            
        # 11. Submissão
        lines.append("11. SUBMISSÃO")
        lines.append("-" * 40)
        if self.current_challenge and self.current_challenge.submission_state:
            lines.append(json.dumps(self.current_challenge.submission_state, indent=2))
        else:
            lines.append("Não identificada")
        lines.append("")
        
        # 12. Validação
        lines.append("12. VALIDAÇÃO")
        lines.append("-" * 40)
        if self.current_challenge and self.current_challenge.validation_state:
            lines.append(json.dumps(self.current_challenge.validation_state, indent=2))
        else:
            lines.append("Não identificada")
        lines.append("")
        
        # 13. Máquina de Estados
        lines.append("13. MÁQUINA DE ESTADOS")
        lines.append("-" * 40)
        for t in self.state_transitions:
            lines.append(f"  {t.from_state.value} → {t.to_state.value}")
            lines.append(f"    Reason: {t.reason or 'N/A'}")
            lines.append(f"    Evidence: {t.evidence or 'N/A'}")
            lines.append("")
            
        # 14. Trace Cronológico
        lines.append("14. TRACE CRONOLÓGICO")
        lines.append("-" * 40)
        for entry in self.event_trace:
            lines.append(f"  [{entry.timestamp}] {entry.event_type}")
            lines.append(f"    Source: {entry.source}")
            lines.append(f"    Data: {str(entry.data)[:100]}")
            lines.append("")
            
        # 15. Erros
        lines.append("15. ERROS")
        lines.append("-" * 40)
        if self.errors:
            for err in self.errors:
                lines.append(f"  [{err['timestamp']}] {err['context']}")
                lines.append(f"    Type: {err['error_type']}")
                lines.append(f"    Message: {err['error_message']}")
                lines.append("")
        else:
            lines.append("Nenhum erro registrado")
        lines.append("")
        
        # 16. Elementos Desconhecidos
        lines.append("16. ELEMENTOS DESCONHECIDOS")
        lines.append("-" * 40)
        if self.unknowns:
            for unk in self.unknowns:
                lines.append(f"  [{unk['timestamp']}] {unk['description']}")
        else:
            lines.append("Nenhum elemento desconhecido")
        lines.append("")
        
        # 17. Resultado Final
        lines.append("17. RESULTADO FINAL")
        lines.append("-" * 40)
        lines.append(f"Estado: {self.current_state.value}")
        lines.append(f"Challenge ID: {self.current_challenge.challenge_id if self.current_challenge else 'N/A'}")
        lines.append(f"Session ID: {self.current_session.session_id if self.current_session else 'N/A'}")
        lines.append("")
        
        return "\n".join(lines)
        
    async def run_analysis(self, container_url: str):
        """Execução principal do fluxo completo"""
        
        print("=" * 80)
        print("FILECRYPT FORENSIC ANALYZER")
        print("Zero suposições - Apenas evidências observáveis")
        print("=" * 80)
        
        self._trace("analysis_start", {"url": container_url})
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=['--window-size=1400,900', '--disable-web-security', '--disable-features=IsolateOrigins,site-per-process']
            )
            
            context = await browser.new_context(
                viewport={'width': 1400, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            try:
                # Configura captura de rede
                await self._capture_network(page)
                
                # Navega para URL
                self._trace("page_load_start", {"url": container_url})
                await page.goto(container_url, wait_until='networkidle')
                self._trace("page_loaded", {"url": page.url})
                
                # Descobre desafio
                challenge_found = await self._discover_challenge(page)
                
                if not challenge_found:
                    print("AVISO: Desafio não encontrado na página")
                    self._log_unknown("Desafio não encontrado na página inicial")
                    
                # Instrumenta Workers
                await self._instrument_workers(page)
                
                # Monitora DOM
                await self._monitor_dom_changes(page)
                
                # Descobre scripts
                await self._discover_scripts(page)
                
                # Aguarda processamento se desafio foi encontrado
                if challenge_found:
                    await self._wait_for_processing(page)
                    await self._identify_submission(page)
                    await self._validate_with_server(page)
                    
                # Coleta dados finais
                await self._collect_worker_messages(page)
                await self._collect_dom_mutations(page)
                
                # Coleta cookies da sessão
                cookies = await context.cookies()
                if self.current_session:
                    self.current_session.cookies = cookies
                else:
                    self.current_session = SessionContext(cookies=cookies)
                    
            except Exception as e:
                self._log_error("run_analysis", e)
                self._transition_state(ChallengeState.ERROR, reason=str(e))
                
            finally:
                # Constrói resultado final
                result = self._build_final_result()
                
                # Gera relatórios
                json_report = json.dumps(result, indent=2, default=str)
                txt_report = self._generate_text_report()
                
                # Salva arquivos
                with open('filecrypt_flow_analysis.json', 'w', encoding='utf-8') as f:
                    f.write(json_report)
                    
                with open('filecrypt_flow_analysis.txt', 'w', encoding='utf-8') as f:
                    f.write(txt_report)
                    
                print("\n" + "=" * 80)
                print("ANÁLISE CONCLUÍDA")
                print("=" * 80)
                print(f"Estado Final: {self.current_state.value}")
                print(f"Arquivos gerados:")
                print(f"  - filecrypt_flow_analysis.json")
                print(f"  - filecrypt_flow_analysis.txt")
                print(f"Total de eventos trace: {len(self.event_trace)}")
                print(f"Total de requests: {len(self.network_requests)}")
                print(f"Total de mensagens Worker: {len(self.worker_messages)}")
                print(f"Total de erros: {len(self.errors)}")
                print(f"Total de unknowns: {len(self.unknowns)}")
                
                await browser.close()
                
        return self.final_result


def main():
    """Ponto de entrada principal"""
    parser = argparse.ArgumentParser(description='FileCrypt Reverse Engineering Tool')
    parser.add_argument('url', help='URL do container FileCrypt para analisar')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout em segundos (padrão: 60)')
    
    args = parser.parse_args()
    
    analyzer = FileCryptAnalyzer()
    
    try:
        asyncio.run(analyzer.run_analysis(args.url))
    except KeyboardInterrupt:
        print("\nAnálise interrompida pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\nErro fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()