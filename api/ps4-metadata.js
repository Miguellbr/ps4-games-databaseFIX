const BASE='https://store.playstation.com/store/api/chihiro/00_09_000/titlecontainer';

function normalizeId(value){
  const s=String(value||'').trim().toUpperCase().replace(/_00$/,'');
  const m=s.match(/CUSA\d{5}/);
  return m?m[0]:'';
}

async function fetchLocale(id,country,language){
  const url=`${BASE}/${country}/${language}/999/${id}_00`;
  try{
    const r=await fetch(url,{headers:{'User-Agent':'PS4-Games-Database-Metadata/1.0','Accept':'application/json'}});
    if(!r.ok)return null;
    const data=await r.json();
    const description=findText(data,['description','long_description','short_description']);
    const name=findText(data,['name','title']);
    const contentId=findContentId(data);
    return {description,name,contentId};
  }catch(_){return null;}
}

function findText(node,keys){
  if(!node)return '';
  if(Array.isArray(node)){
    for(const value of node){const v=findText(value,keys);if(v)return v;}
    return '';
  }
  if(typeof node==='object'){
    for(const key of keys){
      if(typeof node[key]==='string'&&node[key].trim())return node[key].trim().replace(/\s+/g,' ');
    }
    for(const value of Object.values(node)){const v=findText(value,keys);if(v)return v;}
  }
  return '';
}

function findContentId(node){
  if(!node)return '';
  if(Array.isArray(node)){
    for(const value of node){const v=findContentId(value);if(v)return v;}
    return '';
  }
  if(typeof node==='object'){
    for(const key of ['product_id','productId','content_id','contentId','id']){
      const v=node[key];
      if(typeof v==='string'&&v.includes('-')&&v.length>=25)return v;
    }
    for(const value of Object.values(node)){const v=findContentId(value);if(v)return v;}
  }
  return '';
}

async function one(id){
  const en=await fetchLocale(id,'us','en');
  const pt=await fetchLocale(id,'br','pt');
  const ptFallback=pt||await fetchLocale(id,'pt','pt');
  return {
    title_id:id,
    cover_url:`${BASE}/us/en/999/${id}_00/image`,
    description_en:en?.description||'',
    description_pt:ptFallback?.description||'',
    metadata_source:'PlayStation Store',
    metadata_content_id:en?.contentId||ptFallback?.contentId||''
  };
}

export default async function handler(request){
  const url=new URL(request.url);
  const ids=[...new Set((url.searchParams.get('ids')||'').split(',').map(normalizeId).filter(Boolean))].slice(0,20);
  if(!ids.length)return Response.json({games:[]},{status:400});
  const games=[];
  for(let i=0;i<ids.length;i+=4){
    const batch=await Promise.all(ids.slice(i,i+4).map(one));
    games.push(...batch);
  }
  return Response.json({games},{
    headers:{
      'Cache-Control':'public, s-maxage=86400, stale-while-revalidate=604800'
    }
  });
}
