const BASE = 'https://store.playstation.com/store/api/chihiro/00_09_000/titlecontainer';

function normalizeId(value) {
  const s = String(value || '').trim().toUpperCase().replace(/_00$/, '');
  const m = s.match(/CUSA\d{5}/);
  return m ? m[0] : '';
}

async function fetchLocale(id, country, language) {
  const url = `${BASE}/${country.toUpperCase()}/${language.toLowerCase()}/999/${id}_00`;
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

function findText(node, keys) {
  if (!node) return '';
  if (Array.isArray(node)) {
    for (const value of node) {
      const v = findText(value, keys);
      if (v) return v;
    }
    return '';
  }
  if (typeof node !== 'object') return '';

  for (const key of keys) {
    const value = node[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim().replace(/\s+/g, ' ');
    }
  }

  for (const value of Object.values(node)) {
    const v = findText(value, keys);
    if (v) return v;
  }
  return '';
}

function findImage(node) {
  if (!node) return '';
  if (Array.isArray(node)) {
    for (const value of node) {
      const v = findImage(value);
      if (v) return v;
    }
    return '';
  }
  if (typeof node !== 'object') return '';

  if (Array.isArray(node.images)) {
    const preferred = node.images.find(x => x && x.url && [1, 12, 13].includes(Number(x.type)));
    if (preferred?.url) return preferred.url;
    const first = node.images.find(x => x && typeof x.url === 'string');
    if (first?.url) return first.url;
  }

  for (const value of Object.values(node)) {
    const v = findImage(value);
    if (v) return v;
  }
  return '';
}

const TUMBLER = 'https://store.playstation.com/store/api/chihiro/00_09_000/tumbler/SA/en/999';

function normalizeName(value) {
  return String(value || '').replace(/[®™]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function nameScore(value, wanted) {
  const a = normalizeName(value);
  const b = normalizeName(wanted);
  if (!a || !b) return 0;
  if (a === b) return 100;
  if (a.includes(b) || b.includes(a)) return 80;
  const aw = new Set(a.split(/\\s+/).filter(Boolean));
  const bw = new Set(b.split(/\\s+/).filter(Boolean));
  const common = [...aw].filter(x => bw.has(x)).length;
  if (!common) return 0;
  return Math.round(50 * common / Math.max(aw.size, bw.size));
}

function collectCusas(node, out = new Set(), depth = 0, seen = new Set()) {
  if (depth > 10 || node == null) return out;
  if (typeof node === 'string') {
    const id = normalizeId(node);
    if (id) out.add(id);
    return out;
  }
  if (typeof node !== 'object' || seen.has(node)) return out;
  seen.add(node);
  for (const [key, value] of Object.entries(node)) {
    const keyName = String(key).toLowerCase();
    if (typeof value === 'string') {
      const id = normalizeId(value);
      if (id || /cusa|title.?id|product.?id|content.?id|concept.?id|sku/i.test(keyName)) {
        if (id) out.add(id);
      }
    }
    collectCusas(value, out, depth + 1, seen);
  }
  return out;
}

function findMatchingCusa(node, wantedName) {
  let best = { id: '', score: 0 };
  const seen = new Set();

  function subtree(value, depth) {
    if (depth > 12 || value == null) return { score: 0, ids: new Set() };
    if (typeof value === 'string') {
      const id = normalizeId(value);
      return { score: 0, ids: id ? new Set([id]) : new Set() };
    }
    if (typeof value !== 'object' || seen.has(value)) return { score: 0, ids: new Set() };
    seen.add(value);

    let score = 0;
    const ids = new Set();

    for (const [key, child] of Object.entries(value)) {
      if (typeof child === 'string') {
        const id = normalizeId(child);
        if (id) ids.add(id);
        score = Math.max(score, nameScore(child, wantedName));
        if (/cusa|title.?id|product.?id|content.?id|concept.?id|sku/i.test(key) && id) ids.add(id);
      } else {
        const sub = subtree(child, depth + 1);
        score = Math.max(score, sub.score);
        for (const id of sub.ids) ids.add(id);
      }
    }

    return { score, ids };
  }

  function walk(value, depth) {
    if (depth > 12 || value == null || typeof value !== 'object' || seen.has(value)) return;
    const result = subtree(value, depth);
    if (result.score > 0 && result.ids.size) {
      for (const id of result.ids) {
        const exactBonus = result.score === 100 ? 20 : 0;
        const score = result.score + exactBonus;
        if (score > best.score) best = { id, score };
      }
    }
  }

  // Evaluate likely result objects first, then the whole response.
  if (Array.isArray(node)) {
    for (const item of node) walk(item, 0);
  } else {
    walk(node, 0);
  }
  return best.id;
}

async function resolveName(name) {
  const clean=String(name||'').trim(); if(!clean)return null;
  const variants = [...new Set([
    clean,
    clean.replace(/[#]/g, ''),
    clean.replace(/[®™]/g, ''),
    clean.replace(/[:'’&]/g, ' '),
    clean.replace(/[-_]/g, ' ')
  ].map(x => x.replace(/\\s+/g, ' ').trim()).filter(Boolean))];

  const regions = [
    ['SA','en'],
    ['US','en'],
    ['GB','en'],
    ['BR','pt']
  ];

  try {
    let best = null;
    for (const [country, language] of regions) {
      for (const variant of variants) {
        const q=encodeURIComponent(variant.replace(/\\s+/g,'_'));
        const url=TUMBLER.replace('/SA/en/','/' + country + '/' + language + '/') + '/' + q + '?suggested_size=50&mode=game';
        const r=await fetch(url,{headers:{'User-Agent':'Mozilla/5.0 PS4-Games-Database','Accept':'application/json'}});
        if(!r.ok)continue;
        const data=await r.json();
        const id=findMatchingCusa(data,clean);
        if(id) {
          return {name:clean,title_id:id};
        }
      }
    }
    return best;
  } catch (_) { return null; }
}

async function resolveName(name) {
  const clean=String(name||'').trim(); if(!clean)return null;
  try {
    const q=encodeURIComponent(clean.replace(/\s+/g,'_'));
    const url=TUMBLER+'/'+q+'?suggested_size=20&mode=game';
    const r=await fetch(url,{headers:{'User-Agent':'Mozilla/5.0 PS4-Games-Database','Accept':'application/json'}});
    if(!r.ok)return null;
    const data=await r.json(), id=findMatchingCusa(data,clean);
    return id?{name:clean,title_id:id}:null;
  } catch (_) { return null; }
}

async function one(id) {
  const [en, pt] = await Promise.all([
    fetchLocale(id, 'US', 'en'),
    fetchLocale(id, 'BR', 'pt')
  ]);

  const ptData = pt || await fetchLocale(id, 'PT', 'pt');
  const enData = en || await fetchLocale(id, 'GB', 'en');

  const descriptionKeys = [
    'description',
    'long_description',
    'longDescription',
    'long_desc',
    'short_description',
    'shortDescription',
    'short_desc',
    'synopsis'
  ];

  const cover =
    findImage(enData) ||
    findImage(ptData) ||
    `${BASE}/US/en/999/${id}_00/image`;

  return {
    title_id: id,
    cover_url: cover,
    description_en: findText(enData, descriptionKeys),
    description_pt: findText(ptData, descriptionKeys),
    metadata_source: 'PlayStation Store'
  };
}

module.exports = async function handler(req, res) {
  try {
    const rawValue = req.query && req.query.ids;
    const raw = Array.isArray(rawValue)
      ? (rawValue[0] || '')
      : String(rawValue || '');

    const ids = [...new Set(raw.split(',').map(normalizeId).filter(Boolean))].slice(0, 20);
    let names = [];
    const rawNames = req.query && req.query.names;
    if (rawNames) {
      try {
        const parsed = JSON.parse(Array.isArray(rawNames) ? rawNames[0] : String(rawNames));
        if (Array.isArray(parsed)) names = parsed.map(x => String(x || '').trim()).filter(Boolean).slice(0, 20);
      } catch (_) {}
    }
    const resolved = [];
    for (let i = 0; i < names.length; i += 4) {
      const batch = await Promise.all(names.slice(i, i + 4).map(resolveName));
      resolved.push(...batch.filter(Boolean));
    }
    for (const item of resolved) if (!ids.includes(item.title_id)) ids.push(item.title_id);
    const limitedIds = ids.slice(0, 20);
    if (!limitedIds.length) return res.status(400).json({ games: [], error: 'No valid CUSA IDs or game names' });
    const games = [];
    for (const item of resolved) {
      const meta = await one(item.title_id);
      if (meta) meta.requested_name = item.name;
      if (meta) games.push(meta);
    }
    const resolvedIds = new Set(resolved.map(x => x.title_id));
    const remainingIds = limitedIds.filter(id => !resolvedIds.has(id));
    for (let i = 0; i < remainingIds.length; i += 4) {
      const batch = await Promise.all(remainingIds.slice(i, i + 4).map(one));
      games.push(...batch);
    }

    res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800');
    return res.status(200).json({ games });
  } catch (error) {
    console.error('PS4 metadata error:', error);
    return res.status(500).json({ games: [], error: 'Metadata service failed' });
  }
};
