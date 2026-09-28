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
async function one(id) {
  const regions = [
    ['US', 'en'],
    ['GB', 'en'],
    ['SA', 'en'],
    ['BR', 'pt'],
    ['PT', 'pt']
  ];

  const responses = await Promise.all(
    regions.map(([country, language]) => fetchLocale(id, country, language))
  );

  const enData = responses[0] || responses[1] || responses[2];
  const ptData = responses[3] || responses[4];

  const descriptionKeys = [
    'description',
    'long_description',
    'longDescription',
    'long_desc',
    'short_description',
    'shortDescription',
    'short_desc',
    'default_description',
    'defaultDescription',
    'synopsis',
    'summary'
  ];

  const description_en = findText(enData, descriptionKeys);
  const description_pt = findText(ptData, descriptionKeys);
  const cover =
    findImage(enData) ||
    findImage(ptData) ||
    `${BASE}/us/en/999/${id}_00/image`;

  const hasData = !!(enData || ptData || description_en || description_pt || cover);
  if (!hasData) return null;

  return {
    title_id: id,
    cover_url: cover,
    description_en,
    description_pt,
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
