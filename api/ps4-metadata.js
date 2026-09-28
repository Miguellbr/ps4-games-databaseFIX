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

function findMatchingCusa(node, wantedName) {
  const wanted = normalizeName(wantedName), seen = new Set();
  function walk(value, depth) {
    if (depth > 7 || value == null) return '';
    if (typeof value === 'string') return normalizeId(value);
    if (typeof value !== 'object' || seen.has(value)) return '';
    seen.add(value);
    const strings = Object.values(value).filter(v => typeof v === 'string');
    const hasWanted = strings.some(v => { const n=normalizeName(v); return n===wanted || n.includes(wanted) || wanted.includes(n); });
    if (hasWanted) { for (const s of strings) { const id=normalizeId(s); if(id)return id; } }
    for (const child of Object.values(value)) { const id=walk(child,depth+1); if(id)return id; }
    return '';
  }
  return walk(node,0);
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
