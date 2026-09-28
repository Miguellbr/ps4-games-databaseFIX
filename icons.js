(() => {
  const icons = {
    app: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 7.5h11A3.5 3.5 0 0 1 21 11v4a3.5 3.5 0 0 1-3.5 3.5h-1.2a2 2 0 0 1-1.7-.95L13.7 16h-3.4l-.9 1.55a2 2 0 0 1-1.7.95H6.5A3.5 3.5 0 0 1 3 15v-4a3.5 3.5 0 0 1 3.5-3.5Z"/><path d="M8 11v4M6 13h4M16 12h.01M18.5 14h.01"/></svg>',
    filter: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="12" cy="18" r="1.5"/></svg>',
    favorite: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 19.2-1.15-1.05C6.2 13.9 3.5 11.4 3.5 8.35A4.35 4.35 0 0 1 7.85 4 4.9 4.9 0 0 1 12 6.3 4.9 4.9 0 0 1 16.15 4a4.35 4.35 0 0 1 4.35 4.35c0 3.05-2.7 5.55-7.35 9.8Z"/></svg>',
    history: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.35-5.65L4 8.7M4 4.5v4.2h4.2"/><path d="M12 8v4l2.8 1.7"/></svg>',
    theme: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v2M12 19v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M3 12h2M19 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42"/><circle cx="12" cy="12" r="4"/></svg>',
    import: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v11M8 10l4 4 4-4M5 17v2.5A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V17"/><path d="M5 17h14"/></svg>',
    export: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21V10M8 14l4-4 4 4M5 7V4.5A1.5 1.5 0 0 1 6.5 3h11A1.5 1.5 0 0 1 19 4.5V7"/></svg>',
    guide: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4.5A2.5 2.5 0 0 1 8.5 2H19v17H8.5A2.5 2.5 0 0 0 6 21.5V4.5Z"/><path d="M6 4.5v17M10 7h5M10 10h6M10 13h4"/></svg>',
    language: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    credits: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 14.6 9l5.9.8-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1L9.4 9 12 3.5Z"/><path d="M8 20.5h8"/></svg>',
    package: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.3v9.4L12 21l-8-4.3V7.3L12 3Z"/><path d="M4.4 7.5 12 12l7.6-4.5M12 12v9M8 5.2l8 4.4"/></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.3"/><path d="m16 16 4.5 4.5"/></svg>',
    controls: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 17h14"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="17" r="2"/></svg>'
  };

  const css = document.createElement('style');
  css.textContent = `
    .app-icon{display:inline-flex;width:1.12em;height:1.12em;vertical-align:-.18em;margin-right:.48em;color:var(--accent2);flex:none}
    .app-icon svg{width:100%;height:100%;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    .side-btn .app-icon,.filter-toggle .app-icon,.filter-heading .app-icon{width:18px;height:18px;margin-right:9px;vertical-align:-4px}
    .menu-title-icon{width:22px;height:22px;margin-right:7px;vertical-align:-5px}
    .hero-icon{width:1.05em;height:1.05em;margin-right:.16em;vertical-align:-.1em;color:var(--accent)}
    .theme-mode .app-icon{color:var(--accent2)}
    .credits-card{line-height:1.65}.credits-card h3{margin:18px 0 7px}.credits-card p{color:var(--muted)}.credits-card a{color:var(--accent2);font-weight:700;text-decoration:none}.credits-card a:hover{text-decoration:underline}
    .dpi-notice{margin:0 0 15px;padding:11px 13px;border:1px solid var(--accent-line);border-radius:12px;background:var(--accent-soft);color:var(--text);font-size:12px;line-height:1.5}
  `;
  document.head.appendChild(css);

  document.querySelectorAll('[data-icon]').forEach(el => {
    const name = el.dataset.icon;
    if (!icons[name]) return;
    const span = document.createElement('span');
    span.className = 'app-icon' + (el.dataset.iconClass ? ' '+el.dataset.iconClass : '');
    span.innerHTML = icons[name];
    el.replaceWith(span);
  });
})();