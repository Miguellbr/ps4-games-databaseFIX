#!/usr/bin/env python3
"""
FileCrypt Reverse Engineering Tool - file-rev.py
Ferramenta automatizada de processamento do fluxo de verificação do FileCrypt.

Arquitetura: URL → DESCOBERTA → DESAFIO → SESSÃO → PROCESSAMENTO → ENVIO → VALIDAÇÃO → RESULTADO

CORREÇÕES:
1. Worker instrumentado ANTES da navegação
2. Processamento real implementado (PoW solver)
3. Validação analisa conteúdo da resposta
4. Request/Response correlacionados por ID único
5. Componente de processamento ativo, não apenas observação
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
from typing import Dict, List, Optional, Any, Tuple, Callable
from enum import Enum, auto
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Request, Response, Route


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
    script_type: str = "UNKNOWN"
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class WorkerMessage:
    """Mensagem de/para Worker"""
    timestamp: str
    direction: str
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
    classification: str = "OTHER"
    related_challenge: Optional[str] = None
    related_session: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NetworkResponse:
    """Response de rede capturado"""
    request_id: str  # Mesmo ID do request para correlação
    timestamp: str
    status: int
    url: str
    content_type: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    size: int = 0
    body: Optional[str] = None
    parsed_body: Optional[Dict] = None  # Body parseado quando possível
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EventTraceEntry:
    """Entrada do trace cronológico"""
    timestamp: str
   