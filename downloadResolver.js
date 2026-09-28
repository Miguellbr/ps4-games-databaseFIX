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
            // Tenta carregar do mesmo diretório do catalog.json
            const response = await fetch('src/data/resolved_links.json');
            if (!response.ok) throw new Error('resolved_links.json not found');
            
            const data = await response.json();
            this.resolvedLinks = data.resolutions || {};
            this.metadata = data.metadata || {};
            this.loaded = true;
            
            console.log(`[DownloadResolver] Loaded ${Object.keys(this.resolvedLinks).length} resolved links`);
            return true;
            
        } catch (error) {
            console.warn('[DownloadResolver] Could not load resolved links:', error);
            this.resolvedLinks = {};
            return false;
        }
    }
    
    /**
     * Resolve um link FileCrypt para direto
     * @param {string} url - URL original
     * @param {string} gameTitle - Título do jogo
     * @param {string} host - Tipo de host (mediafire, 1file, etc)
     * @param {number} index - Índice do link
     * @returns {Object} {url, isResolved, isFilecrypt, badge}
     */
    resolveLink(url, gameTitle, host, index = 0) {
        // Se não for FileCrypt, retorna como está
        if (!url || !url.toLowerCase().includes('filecrypt')) {
            return {
                url: url,
                isResolved: false,
                isFilecrypt: false,
                badge: null
            };
        }
        
        // Tenta encontrar no mapa de resolvidos
        const linkId = `${gameTitle}__${host}__${index}`;
        const resolution = this.resolvedLinks?.[linkId];
        
        if (resolution?.resolved && resolution.direct_url) {
            return {
                url: resolution.direct_url,
                isResolved: true,
                isFilecrypt: true,
                badge: '⚡ DIRECT',
                originalUrl: url
            };
        }
        
        // FileCrypt não resolvido
        return {
            url: url,
            isResolved: false,
            isFilecrypt: true,
            badge: '🔒 FILECRYPT',
            originalUrl: url
        };
    }
    
    /**
     * Cria elemento de link de download (substitui a função add() original)
     * Use esta função no lugar de criar <a> diretamente
     */
    createDownloadLink(url, gameTitle, host, index, label) {
        const resolved = this.resolveLink(url, gameTitle, host, index);
        
        const a = document.createElement('a');
        a.href = resolved.url;
        a.className = `download-btn btn-${host} ${resolved.isResolved ? 'btn-resolved' : ''}`;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        
        // Texto do botão
        const badge = resolved.badge ? ` [${resolved.badge}]` : '';
        a.textContent = `${label} ${index + 1}${badge}`;
        
        // Se for FileCrypt não resolvido, adiciona handler de confirmação
        if (resolved.isFilecrypt && !resolved.isResolved) {
            a.onclick = (e) => this.handleFilecryptClick(e, resolved.originalUrl, gameTitle);
            a.title = 'Via FileCrypt (requires CAPTCHA)';
        } else if (resolved.isResolved) {
            a.title = 'Direct link (no CAPTCHA)';
        }
        
        return a;
    }
    
    /**
     * Handler para clique em FileCrypt não resolvido
     */
    handleFilecryptClick(event, originalUrl, gameTitle) {
        const proceed = confirm(
            `⚠️ "${gameTitle}"\n\n` +
            `This link goes through FileCrypt (CAPTCHA required).\n` +
            `Would you like to:\n\n` +
            `• OK: Go to FileCrypt\n` +
            `• Cancel: Wait for automatic resolution\n\n` +
            `Note: Run "python src/scripts/resolve_catalog.py" to resolve all links.`
        );
        
        if (!proceed) {
            event.preventDefault();
            return false;
        }
        
        return true;
    }
    
    /**
     * Gera todos os botões de download para um jogo
     * Substitui o bloco add() no seu código
     */
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

// Instância global
const downloadResolver = new DownloadResolver();

// Exporta para uso
window.DownloadResolver = DownloadResolver;
window.downloadResolver = downloadResolver;