import asyncio
import json
import uuid
import time
import hashlib
from datetime import datetime
from playwright.async_api import async_playwright
import re
import os
import sys


class FileCryptAnalyzer:
    """
    Análise forense completa do FileCrypt CAPTCHA.
    ZERO suposições - apenas dados observados.
    """

    def __init__(self):
        # Inicialização completa
        self.scripts = {}  # name -> content
        self.scripts_metadata = {}  # name -> {url, size, hash}
        self.network_log = []
        self.request_map = {}
        self.captcha_requests = []
        self.worker_messages = []
        self.worker_message_pairs = []  # input -> output correlation
        self.form_fields_log = []
        self.dom_events = []
        self.validation_events = []
        self.completion_signals = []
        self.session_data = {}
        self.session_request = None
        self.captcha_config = {}
        self.event_trace = []  # Trace cronológico único
        self._last_form_hash = None
        self._captcha_completed = False
        self._validation_candidates = []
        self._worker_url = None
        self._algorithm_evidence = []
        self._flow_spec = []

    def _trace(self, event_type, data, source="analyzer"):
        """Registra evento no trace cronológico"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'source': source,
            'data': data
        }
        self.event_trace.append(entry)
        # Log em tempo real para debug
        print(f"[TRACE:{event_type}] {str(data)[:100]}")

    async def run_analysis(self, container_url):
        """Execução principal"""
        print("=" * 70)
        print("FILECRYPT FORENSIC ANALYZER")
        print("Zero suposições - Apenas evidências")
        print("=" * 70)
        
        self._trace("analysis_start", {"url": container_url})
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=['--window-size=1400,900', '--disable-web-security']
            )
            
            context = await browser.new_context(
                viewport={'width': 1400, 'height': 900}
            )
            