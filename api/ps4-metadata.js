const BASE = 'https://store.playstation.com/store/api/chihiro/00_09_000/titlecontainer';
const TUMBLER = 'https://store.playstation.com/store/api/chihiro/00_09_000/tumbler/SA/en/999';

function normalizeId(value) {
  const m = String(value || '').trim().toUpperCase().match(/CUSA\d{5}/);
  return m ? m[0] : '';
}

async function fetchJson(url) {
  try {
    const r = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 PS4-Games-Database',
        'Accept': 'application/json'
      }
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}

async function fetchLocale(id, country, language) {
  const cc = country.toLowerCase();
  const lang = language.toLowerCase();
  return await fetchJson(`${BASE}/${cc}/${lang}/999/${id}_00`);
}

function findText(node, keys) {
  if (!node) return '';
  const wanted = new Set(keys.map(k => String(k).toLowerCase()));

  function walk(value, depth = 0) {
    if (!value || depth > 12) return '';
    if (Array.isArray(value)) {
      for (const item of value) {
        const found = walk(item, depth + 1);
        if (found) return found;
      }
      return '';
    }
    if (typeof value !== 'object') return '';

    for (const [key, child] of Object.entries(value)) {
      if (typeof child === 'string' && child.trim() &&
          (wanted.has(key.toLowerCase()) || /description|synopsis|summary/.test(key.toLowerCase()))) {
        return child.trim().replace(/\s+/g, ' ');
      }
    }
    for (const child of Object.values(value)) {
      const found = walk(child, depth + 1);
      if (found) return found;
    }
    return '';
  }

  return walk(node);
}

function findImage(node) {
  if (!node) return '';
  if (Array.isArray(node)) {
    for (const item of node) {
      const found = findImage(item);
      if (found) return found;
    }
    return '';
  }
  if (typeof node !== 'object') return '';

  if (Array.isArray(node.images)) {
    const preferred = node.images.find(x => x && typeof x.url === 'string' && [1, 12, 13].includes(Number(x.type)));
    if (preferred?.url) return preferred.url;
    const first = node.images.find(x => x && typeof x.url === 'string');
    if (first?.url) return first.url;
  }

  for (const child of Object.values(node)) {
    const found = findImage(child);
    if (found) return found;
  }
  return '';
}

function normalizeName(value) {
  return String(value || '').replace(/[®™]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function nameScore(value, wanted) {
  const a = normalizeName(value);
  const b = normalizeName(wanted);
  if (!a || !b) return 0;
  if (a === b) return 100;
  if (a.includes(b) || b.includes(a)) return 80;
  const aw = new Set(a.split(/\s+/));
  const bw = new Set(b.split(/\s+/));
  const common = [...aw].filter(x => bw.has(x)).length;
  return common ? Math.round(50 * common / Math.max(aw.size, bw.size)) : 0;
}

function findMatchingCusa(node, wantedName) {
  let best = { id: '', score: 0 };

  function walk(value, depth = 0) {
    if (!value || depth > 10) return;
    if (Array.isArray(value)) {
      for (const item of value) walk(item, depth + 1);
      return;
    }
    if (typeof value !== 'object') return;

    let localScore = 0;
    const ids = new Set();

    for (const [key, child] of Object.entries(value)) {
      if (typeof child === 'string') {
        const id = normalizeId(child);
        if (id) ids.add(id);
        const score = nameScore(child, wantedName);
        if (score > localScore) localScore = score;
      }
      if (child && typeof child === 'object') walk(child, depth + 1);
    }

    const titleFields = ['name', 'title', 'label', 'displayName', 'conceptName'];
    for (const key of titleFields) {
      if (typeof value[key] === 'string') {
        const score = nameScore(value[key], wantedName);
        if (score > localScore) localScore = score;
      }
    }

    for (const child of Object.values(value)) {
      if (typeof child === 'string') {
        const id = normalizeId(child);
        if (id) ids.add(id);
      }
    }

    if (localScore && ids.size) {
      for (const id of ids) {
        const score = localScore + (localScore === 100 ? 20 : 0);
        if (score > best.score) best = { id, score };
      }
    }
  }

  walk(node);
  return best.id;
}

async function resolveName(name) {
  const clean = String(name || '').trim();
  if (!clean) return null;

  const variants = [...new Set([
    clean,
    clean.replace(/[#]/g, ''),
    clean.replace(/[®™]/g, ''),
    clean.replace(/[:'’&]/g, ' '),
    clean.replace(/[-_]/g, ' ')
  ].map(x => x.replace(/\s+/g, ' ').trim()).filter(Boolean))];

  for (const variant of variants) {
    const q = encodeURIComponent(variant.replace(/\s+/g, '_'));
    const data = await fetchJson(`${TUMBLER}/${q}?suggested_size=20&mode=game`);
    const id = findMatchingCusa(data, clean);
    if (id) return { name: clean, title_id: id };
  }
  return null;
}

async function one(id) {
  const [en, pt] = await Promise.all([
    fetchLocale(id, 'US', 'en'),
    fetchLocale(id, 'BR', 'pt')
  ]);

  const [enFallback, ptFallback] = await Promise.all([
    en ? Promise.resolve(null) : fetchLocale(id, 'GB', 'en'),
    pt ? Promise.resolve(null) : fetchLocale(id, 'PT', 'pt')
  ]);

  const enData = en || enFallback;
  const ptData = pt || ptFallback;

  const descriptionKeys = [
    'description', 'long_description', 'longDescription', 'long_desc',
    'short_description', 'shortDescription', 'short_desc',
    'default_description', 'defaultDescription', 'synopsis', 'summary'
  ];

  if (!enData && !ptData) return null;

  return {
    title_id: id,
    cover_url: findImage(enData) || findImage(ptData) || '',
    description_en: findText(enData, descriptionKeys),
    description_pt: findText(ptData, descriptionKeys),
    metadata_source: 'PlayStation Store'
  };
}

module.exports = async function handler(req, res) {
  try {
    const rawIds = Array.isArray(req.query?.ids) ? req.query.ids[0] : String(req.query?.ids || '');
    const ids = [...new Set(rawIds.split(',').map(normalizeId).filter(Boolean))].slice(0, 20);

    let names = [];
    try {
      const rawNames = Array.isArray(req.query?.names) ? req.query.names[0] : req.query?.names;
      const parsed = rawNames ? JSON.parse(String(rawNames)) : [];
      if (Array.isArray(parsed)) names = parsed.map(x => String(x || '').trim()).filter(Boolean).slice(0, 20);
    } catch (_) {}

    const resolved = [];
    // Only do name resolution when the request contains no usable CUSA IDs.
    // This prevents a batch of known-CUSA games from exploding into dozens of Store searches.
    if (!ids.length) {
      for (let i = 0; i < names.length; i += 4) {
        const batch = await Promise.all(names.slice(i, i + 4).map(resolveName));
        resolved.push(...batch.filter(Boolean));
      }
    }

    for (const item of resolved) {
      if (!ids.includes(item.title_id)) ids.push(item.title_id);
    }

    const limitedIds = ids.slice(0, 20);
    if (!limitedIds.length) {
      return res.status(400).json({ games: [], error: 'No valid CUSA IDs or game names' });
    }

    const games = [];
    for (const id of limitedIds) {
      const meta = await one(id);
      if (meta) games.push(meta);
    }

    // Keep name-based lookup useful for single-name requests without CUSA.
    if (!games.length && names.length) {
      for (const name of names.slice(0, 4)) {
        const item = await resolveName(name);
        if (!item) continue;
        const meta = await one(item.title_id);
        if (meta) games.push({ ...meta, requested_name: item.name });
      }
    }

    res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800');
    return res.status(200).json({ games });
  } catch (error) {
    console.error('PS4 metadata error:', error);
    return res.status(500).json({ games: [], error: 'Metadata service failed' });
  }
};
