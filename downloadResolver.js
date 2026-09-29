/** 
 * DownloadResolver - Integração FileCrypt Bypass
 * Resolve links FileCrypt usando resolved_links.json
 */

class DownloadResolver {
    constructor() {
        this.resolvedLinks = null;
        this.loaded = false;
        this.loadPromise = this.loadResolvedLinks();
    }
    
    async loadResolvedLinks() {
        try {
            const response = await fetch('./src/data/resolved_links.json?resolver=1', { cache: 'no-store' });
            if (!response.ok) throw new Error('resolved_links.json not found');
            
            const data = await response.json();
            this.resolvedLinks = data.resolutions || {};
            this.metadata = data.metadata || {};
            this.loaded = true;
            
            console.log(`[DownloadResolver] Loaded ${Object.keys(this.resolvedLinks).length} link states`);
            return true;
        } catch (error) {
            console.warn('[DownloadResolver] Could not load resolved links:', error);
            this.resolvedLinks = {};
            this.loaded = false;
            return false;
        }
    }

    async waitUntilLoaded() {
        return this.loadPromise;
    }
    
    resolveLink(url, gameTitle, host, index = 0) {
        if (!url || !url.toLowerCase().includes('filecrypt')) {
            return {
                url,
                isResolved: false,
                isFilecrypt: false,
                needsVerification: false,
                badge: null
            };
        }
        
        const linkId = `${gameTitle}__${host}__${index}`;
        const resolution = this.resolvedLinks?.[linkId];
        
        if (resolution?.resolved && resolution.direct_url) {
            return {
                url: resolution.direct_url,
                isResolved: true,
                isFilecrypt: true,
                needsVerification: false,
                badge: '⚡ DIRECT',
                originalUrl: url,
                status: 'resolved'
            };
        }

        const needsVerification =
            resolution?.status === 'needs_verification' ||
            typeof resolution?.error === 'string' &&
            resolution.error.startsWith('needs_verification:');

        return {
            url,
            isResolved: false,
            isFilecrypt: true,
            needsVerification,
            badge: needsVerification ? '🔐 VERIFICAÇÃO' : '🔒 FILECRYPT',
            originalUrl: url,
            status: needsVerification ? 'needs_verification' : (resolution?.status || 'unknown'),
            error: resolution?.error || null
        };
    }
    
    createDownloadLink(url, gameTitle, host, index, label) {
        const resolved = this.resolveLink(url, gameTitle, host, index);
        
        const a = document.createElement('a');
        a.href = resolved.url;
        a.className = `download-btn btn-${host} ${resolved.isResolved ? 'btn-resolved' : ''} ${resolved.needsVerification ? 'btn-verification' : ''}`;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        
        const badge = resolved.isFilecrypt && resolved.badge ? ` [${resolved.badge}]` : '';
        a.textContent = `${label} ${index + 1}${badge}`;
        
        if (resolved.isFilecrypt && !resolved.isResolved) {
            a.onclick = (e) => this.handleFilecryptClick(e, resolved.originalUrl, gameTitle, resolved.needsVerification);
            a.title = resolved.needsVerification
                ? 'FileCrypt requer verificação'
                : 'Via FileCrypt (verification may be required)';
        } else if (resolved.isResolved) {
            a.title = 'Direct link (no CAPTCHA)';
        }
        
        return a;
    }
    
    handleFilecryptClick(event, originalUrl, gameTitle, needsVerification = false) {
        if (!needsVerification) {
            return true;
        }

        const proceed = confirm(
            `⚠️ "${gameTitle}"\n\n` +
            `O resolver identificou que este link do FileCrypt requer verificação.\n\n` +
            `OK: abrir o FileCrypt para realizar a verificação\n` +
            `Cancelar: permanecer nesta página`
        );

        if (!proceed) {
            event.preventDefault();
            return false;
        }

        return true;
    }
    
    renderDownloadLinks(game) {
        const container = document.createElement('div');
        container.className = 'download-links';
        
        const title = game.title || game.name || 'Unknown';
        const links = game.download_links || {};
        
        const addLinks = (arr, host, label) => {
            if (!arr) return;
            const urls = Array.isArray(arr) ? arr : [arr];
            urls.forEach((url, i) => {
                if (url) {
                    const link = this.createDownloadLink(url, title, host, i, label);
                    container.appendChild(link);
                }
            });
        };
        
        addLinks(links.mediafire, 'mediafire', 'Mediafire');
        addLinks(links['1file'], '1file', '1File');
        addLinks(links.other, 'other', 'Mirror');
        addLinks(links.pkg, 'pkg', 'PKG');
        
        return container;
    }
}

const downloadResolver = new DownloadResolver();
window.DownloadResolver = DownloadResolver;
window.downloadResolver = downloadResolver;