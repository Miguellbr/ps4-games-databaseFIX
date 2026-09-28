(() => {
  const nativeApp = !!(window.Capacitor && typeof window.Capacitor.isNativePlatform === 'function' && window.Capacitor.isNativePlatform());
  const DPI_KEY = 'ps4db_dpi_settings';

  const style = document.createElement('style');
  style.textContent = `
    .dpi-modal{position:fixed;inset:0;background:rgba(2,5,10,.74);display:none;align-items:center;justify-content:center;padding:18px;z-index:1400;backdrop-filter:blur(8px)}
    .dpi-modal.show{display:flex}
    .dpi-card{width:min(620px,100%);max-height:90vh;overflow:auto;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:20px;padding:24px;box-shadow:var(--shadow)}
    .dpi-title{font-size:22px;font-weight:800;margin-bottom:5px}
    .dpi-subtitle{color:var(--muted);font-size:13px;line-height:1.5;margin-bottom:18px}
    .dpi-label{display:block;color:var(--muted);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;margin:12px 0 6px}
    .dpi-input{width:100%;height:46px;border:1px solid var(--line);border-radius:11px;background:var(--panel2);color:var(--text);padding:0 13px;outline:0}
    .dpi-input:focus{border-color:var(--accent-line);box-shadow:0 0 0 3px var(--accent-soft)}
    .dpi-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
    .dpi-action{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:10px 14px;border-radius:11px;font-weight:750;cursor:pointer}
    .dpi-action.primary{background:var(--accent);border-color:var(--accent);color:#fff}
    .dpi-action:disabled{opacity:.55;cursor:wait}
    .dpi-status{margin-top:14px;padding:11px 12px;border-radius:11px;background:var(--panel2);border:1px solid var(--line);font-size:12px;color:var(--muted);white-space:pre-wrap}
    .dpi-status.ok{border-color:var(--accent-line);color:var(--accent2);background:var(--accent-soft)}
    .dpi-status.error{border-color:rgba(239,68,68,.35);color:#ef4444}
    .dpi-native{font-size:11px;margin-top:10px;color:var(--muted)}
  `;
  document.head.appendChild(style);

  const settings = (() => {
    try { return JSON.parse(localStorage.getItem(DPI_KEY) || '{}'); } catch { return {}; }
  })();

  function saveSettings() {
    localStorage.setItem(DPI_KEY, JSON.stringify({
      psIp: document.getElementById('dpiPsIp')?.value.trim() || '',
      segmented: !!document.getElementById('dpiSegmented')?.checked
    }));
  }

  function ensureModal() {
    if (document.getElementById('dpiModal')) return;
    const modal = document.createElement('div');
    modal.className = 'dpi-modal';
    modal.id = 'dpiModal';
    modal.onclick = e => { if (e.target === modal) closeDpi(); };
    modal.innerHTML = `
      <div class="dpi-card">
        <button class="modal-close" type="button" onclick="closeDpi()">×</button>
        <div class="dpi-title">PS4 Package Installer</div>
        <div class="dpi-subtitle">Integrated PS4 Games Database installer. It sends a direct PKG URL to your PS4 installation service.</div>${!nativeApp ? '<div class="dpi-notice"><b>Recommended in the app:</b> the installer works better in the APK because it includes the native DPI engine and avoids browser network/CORS restrictions.</div>' : ''}
        <label class="dpi-label" for="dpiPsIp">PS4 IP address</label>
        <input class="dpi-input" id="dpiPsIp" inputmode="decimal" placeholder="192.168.1.100">
        <label class="dpi-label" for="dpiPkgUrl">Direct PKG URL</label>
        <input class="dpi-input" id="dpiPkgUrl" placeholder="https://servidor.exemplo/jogo.pkg">
        <label class="dpi-label"><input id="dpiSegmented" type="checkbox"> Use prepared/segmented mode when supported</label>
        <div class="dpi-actions">
          <button class="dpi-action primary" id="dpiSendBtn" type="button" onclick="sendDpiPackage()">Send to PS4</button>
          <button class="dpi-action" type="button" onclick="closeDpi()">Close</button>
        </div>
        <div class="dpi-status" id="dpiStatus">Waiting for a PKG URL.</div>
        <div class="dpi-native" id="dpiNative"></div><div class="credits-card" style="margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-size:11px"><b>DPI credits</b><br>Integration based on the <a href="https://github.com/marcussacana/DirectPackageInstaller" target="_blank" rel="noopener" style="color:var(--accent2)">DirectPackageInstaller</a>, by <b>marcussacana</b>. The original project is separate; this app implements its own integrated flow.</div>
      </div>`;
    document.body.appendChild(modal);
    document.getElementById('dpiPsIp').value = settings.psIp || '';
    document.getElementById('dpiSegmented').checked = !!settings.segmented;
    document.getElementById('dpiNative').textContent = nativeApp
      ? '✓ Native DPI engine active in the APK.'
      : 'Browser mode: direct communication may be blocked by browser CORS.';
  }

  window.openDpi = function(url='') {
    ensureModal();
    document.getElementById('dpiPkgUrl').value = url || '';
    document.getElementById('dpiStatus').className = 'dpi-status';
    document.getElementById('dpiStatus').textContent = url ? 'URL PKG carregado. Confira o IP do PS4 e envie.' : 'Aguardando um URL de PKG.';
    document.getElementById('dpiModal').classList.add('show');
  };

  window.closeDpi = function() {
    document.getElementById('dpiModal')?.classList.remove('show');
  };

  function parseNativeResult(raw) {
    try { return JSON.parse(raw); } catch { return {ok:false,error:String(raw)}; }
  }

  async function sendNative(psIp, url) {
    if (!window.AndroidDPI) throw new Error('Motor DPI nativo não disponível neste APK.');
    const rpi = parseNativeResult(window.AndroidDPI.sendRpi(psIp, url));
    if (rpi.ok && /success/i.test(rpi.response || '')) return {ok:true,method:'Remote Package Installer',raw:rpi};
    const eta = parseNativeResult(window.AndroidDPI.sendEtaHen(psIp, url));
    if (eta.ok && /success/i.test(eta.response || '')) return {ok:true,method:'etaHEN DPIv2',raw:eta};
    return {ok:false,error:`RPI: ${rpi.response || rpi.error || 'sem resposta'}\netaHEN: ${eta.response || eta.error || 'sem resposta'}`};
  }

  async function sendBrowser(psIp, url) {
    const normalized = url.replace(/^https:\/\//i, 'http://');
    const response = await fetch(`http://${psIp}:12800/api/install`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:'direct',packages:[encodeURIComponent(normalized)]})
    });
    const text = await response.text();
    return {ok:response.ok && /success/i.test(text),method:'Remote Package Installer',raw:text};
  }

  window.sendDpiPackage = async function() {
    ensureModal();
    const psIp = document.getElementById('dpiPsIp').value.trim();
    const url = document.getElementById('dpiPkgUrl').value.trim();
    const status = document.getElementById('dpiStatus');
    const button = document.getElementById('dpiSendBtn');
    if (!psIp || !/^https?:\/\//i.test(url)) {
      status.className='dpi-status error';
      status.textContent='Enter a valid PS4 IP address and a direct HTTP/HTTPS PKG URL.';
      return;
    }
    saveSettings();
    button.disabled=true;
    status.className='dpi-status';
    status.textContent='Testing the PS4 installer…';
    try {
      const result = nativeApp ? await sendNative(psIp,url) : await sendBrowser(psIp,url);
      if (!result.ok) throw new Error(result.error || result.raw || 'The PS4 rejected the request.');
      status.className='dpi-status ok';
      status.textContent=`✓ PKG enviado pelo ${result.method}. The PS4 should start downloading/installing the package.`;
    } catch (e) {
      status.className='dpi-status error';
      status.textContent='Failed to send PKG.\n' + (e?.message || e);
    } finally {
      button.disabled=false;
    }
  };

  function addDpiButton(card) {
    if (!card || card.querySelector('.dpi-card-button')) return;
    const pkg = [...card.querySelectorAll('.download-links a')].find(a => /^PKG\s/i.test(a.textContent || ''));
    if (!pkg || !pkg.href || pkg.href === '#') return;
    const actions = card.querySelector('.game-actions');
    if (!actions) return;
    const b = document.createElement('button');
    b.className='tool-btn dpi-card-button';
    b.type='button';
    b.innerHTML='<span data-icon="package"></span>Enviar ao PS4'; if(window.refreshAppIcons) window.refreshAppIcons(b);
    b.onclick=()=>openDpi(pkg.href);
    actions.appendChild(b);
  }

  function setupCardsObserver() {
    const container = document.getElementById('gamesContainer');
    if (!container) return;
    const scan = () => container.querySelectorAll('.game-item').forEach(addDpiButton);
    new MutationObserver(scan).observe(container,{childList:true,subtree:true});
    scan();
  }

  function setupGuide() {
    const isApp = nativeApp;
    if (typeof I18N === 'undefined') return;
    if (isApp) {
      I18N.pt.guide='Guia do App';
      I18N.pt.guideTitle='Guia do App';
      I18N.pt.guideHtml='<h3>Como usar o app</h3><p>Pesquise jogos normalmente ou abra o menu ☰. O APK inclui o instalador de PKG integrado, sem precisar abrir outro aplicativo.</p><h3>Instalador de PKG</h3><p>Abra <b>☰ → Instalador de PKG</b>, informe o IP do PS4 e use um URL direto de PKG. O app tenta primeiro o Remote Package Installer e depois o etaHEN DPIv2.</p><h3>Requisitos</h3><p>O celular e o PS4 precisam estar na mesma rede local e o PS4 precisa ter um serviço compatível ativo. O URL precisa apontar diretamente para o PKG.</p>';
      I18N.en.guide='App guide';
      I18N.en.guideTitle='App guide';
      I18N.en.guideHtml='<h3>Using the app</h3><p>Search games normally or open the ☰ menu. The APK includes its own PKG installer, so no separate DPI app is required.</p><h3>PKG installer</h3><p>Open <b>☰ → PKG Installer</b>, enter the PS4 IP and use a direct PKG URL. The app tries Remote Package Installer first and etaHEN DPIv2 second.</p><h3>Requirements</h3><p>Your phone and PS4 must be on the same local network and a compatible PS4 service must be active. The URL must point directly to the PKG.</p>';
      if (typeof setLanguage === 'function') setLanguage(localStorage.getItem('ps4db_lang')||'pt');
    }
    const title = document.querySelector('[data-i18n="guideTitle"]');
    if (title) title.textContent = I18N[localStorage.getItem('ps4db_lang')||'pt'].guideTitle;
  }

  function setupMenu() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const old = sidebar.querySelector('#dpiMenuButton');
    if (!old) {
      const b = document.createElement('button');
      b.id='dpiMenuButton';
      b.className='side-btn';
      b.type='button';
      b.innerHTML='<span data-icon="package"></span><span data-i18n="dpiMenu">Instalador de PKG</span>';
      b.onclick=()=>{ openDpi(); if(typeof toggleSidebar==='function') toggleSidebar(false); };
      const guide = [...sidebar.querySelectorAll('.side-btn')].find(x => /Guia do site|Site guide/.test(x.textContent||''));
      if (guide) guide.parentNode.insertBefore(b, guide);
      else sidebar.appendChild(b);
    }
  }

  function init() {
    setupGuide();
    setupMenu();
    updateDpiMenuLanguage();
    window.addEventListener('ps4db-language-changed',updateDpiMenuLanguage);
    setupCardsObserver();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init); else init();
})();