"""Render FeedResult to HTML / JSON / Digest.

Design philosophy: Apple-inspired minimalism.
- Pure white / near-white backgrounds
- Borderless cards with subtle shadows
- Generous whitespace
- Clean sans-serif typography
- Glassmorphism on header only
- Silk-smooth transitions
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from jinja2 import Template

from .models import FeedResult, FeedItem

PLATFORM_META = {
    "v2ex": {"label": "V2EX", "color": "#778087"},
    "github": {"label": "GitHub", "color": "#24292f"},
    "reddit": {"label": "Reddit", "color": "#ff4500"},
    "rss": {"label": "RSS", "color": "#ee802f"},
    "xhs": {"label": "小红书", "color": "#ff2442"},
    "bilibili": {"label": "B站", "color": "#00a1d6"},
    "twitter": {"label": "Twitter", "color": "#1da1f2"},
    "weibo": {"label": "微博", "color": "#e6162d"},
}

HTML_TEMPLATE_STR = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#ffffff">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="referrer" content="no-referrer">
<link rel="manifest" href="manifest.json">
<title>OmniFeed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#f5f5f7;
  --card:#ffffff;
  --text:#1d1d1f;
  --text2:#6e6e73;
  --text3:#86868b;
  --border:rgba(0,0,0,0.04);
  --shadow:0 1px 3px rgba(0,0,0,0.04);
  --shadow-hover:0 12px 32px -8px rgba(0,0,0,0.1);
  --r:16px;
  --ease:cubic-bezier(0.25,0.46,0.45,0.94);
}
body{
  font-family:'Inter',-apple-system,'SF Pro Display','PingFang SC','Helvetica Neue',sans-serif;
  background:var(--bg);color:var(--text);
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
}

/* ── Header ── */
.header{
  position:sticky;top:0;z-index:100;
  padding:14px 24px;
  background:rgba(255,255,255,0.72);
  backdrop-filter:saturate(180%) blur(20px);
  -webkit-backdrop-filter:saturate(180%) blur(20px);
  border-bottom:1px solid rgba(0,0,0,0.06);
  display:flex;align-items:center;gap:12px;
}
.header h1{font-size:17px;font-weight:700;letter-spacing:-0.3px;color:var(--text)}
.header .meta{font-size:11px;color:var(--text3);margin-left:auto;font-weight:500}
.header .rfr{
  margin-left:8px;padding:6px 16px;
  border-radius:20px;border:1px solid rgba(0,0,0,0.1);
  background:#fff;color:var(--text);
  font-size:12px;font-weight:600;cursor:pointer;
  transition:all 0.25s var(--ease);
  font-family:inherit;
}
.header .rfr:hover{background:var(--text);color:#fff;border-color:var(--text)}
.header .rfr:active{transform:scale(0.96)}

/* ── Nav tabs ── */
.nav{
  display:flex;gap:0;
  padding:0 20px;
  background:#fff;
  border-bottom:1px solid rgba(0,0,0,0.06);
  overflow-x:auto;scrollbar-width:none;
  -webkit-overflow-scrolling:touch;
}
.nav::-webkit-scrollbar{display:none}
.nav-item{
  padding:12px 16px;
  font-size:13px;font-weight:500;
  color:var(--text3);
  cursor:pointer;
  border-bottom:2px solid transparent;
  white-space:nowrap;flex-shrink:0;
  transition:all 0.25s var(--ease);
}
.nav-item:hover{color:var(--text)}
.nav-item.on{color:var(--text);border-bottom-color:var(--text);font-weight:600}

/* ── Filter pills ── */
.pills{
  padding:12px 20px 8px;
  display:flex;gap:8px;
  overflow-x:auto;scrollbar-width:none;
  -webkit-overflow-scrolling:touch;
}
.pills::-webkit-scrollbar{display:none}
.pill{
  padding:6px 16px;
  border-radius:20px;
  border:1px solid rgba(0,0,0,0.08);
  background:#fff;
  color:var(--text2);
  font-size:12px;font-weight:500;
  cursor:pointer;
  transition:all 0.2s var(--ease);
  white-space:nowrap;flex-shrink:0;
}
.pill:hover{border-color:rgba(0,0,0,0.15);color:var(--text)}
.pill.on{background:var(--text);color:#fff;border-color:var(--text)}

/* ── Masonry grid (CSS columns) ── */
.grid{
  columns:3;column-gap:16px;
  padding:12px 20px 40px;
  max-width:1100px;margin:0 auto;
}
.grid .card{break-inside:avoid;margin-bottom:16px;display:inline-block;width:100%}
@media(max-width:640px){.grid{columns:1;padding:8px 16px 40px}}
@media(min-width:641px) and (max-width:959px){.grid{columns:2}}
@media(min-width:960px){.grid{columns:3}}

/* ── Card ── */
.card{
  overflow:hidden;
  margin-bottom:16px;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--r);
  overflow:hidden;
  cursor:pointer;
  box-shadow:var(--shadow);
  transition:transform 0.3s var(--ease), box-shadow 0.3s var(--ease);
  position:relative;
}
.card:hover{
  transform:translateY(-4px);
  box-shadow:var(--shadow-hover);
}
.card:active{transform:translateY(-2px) scale(0.99)}

.card img.cover{
  width:100%;display:block;
  max-height:200px;object-fit:cover;
  background:#f0f0f0;
}
.card .body{padding:16px 16px 14px}
.card .source{
  display:inline-block;
  font-size:11px;font-weight:600;
  letter-spacing:0.2px;
  margin-bottom:8px;
  opacity:0.7;
}
.card .title{
  font-size:14px;font-weight:600;
  line-height:1.55;
  color:var(--text);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  letter-spacing:-0.1px;
}
.card .desc{
  font-size:12px;line-height:1.6;
  color:var(--text2);
  margin-top:6px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}
.card .author{
  font-size:11px;color:var(--text3);
  margin-top:4px;font-weight:500;
}
.card .foot{
  display:flex;gap:8px;align-items:center;
  margin-top:10px;flex-wrap:wrap;
}
.card .foot span{font-size:10px;color:var(--text3);font-weight:500}
.card .tag{
  font-size:10px;
  padding:2px 8px;
  border-radius:6px;
  background:#f5f5f7;
  color:var(--text2);
  font-weight:500;
}
.card .reason{
  font-size:11px;color:var(--text3);
  margin-top:8px;font-style:italic;
  opacity:0.8;
}

/* ── Fav button ── */
.card .fav{
  position:absolute;top:10px;right:10px;
  width:32px;height:32px;border-radius:50%;
  background:rgba(255,255,255,0.85);
  backdrop-filter:blur(8px);
  border:none;
  font-size:14px;
  cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  opacity:0;
  transition:all 0.2s var(--ease);
  box-shadow:0 2px 8px rgba(0,0,0,0.08);
}
.card:hover .fav,.card .fav.saved{opacity:1}
.card .fav.saved{background:rgba(255,59,48,0.9);color:#fff}
.card .fav:active{transform:scale(1.15)}

/* ── Sections ── */
.section{display:none}
.section.show{display:block}

/* ── Cluster card ── */
.cluster{
  break-inside:avoid;margin-bottom:16px;display:inline-block;width:100%;
  background:var(--card);
  border:1px solid var(--border);
  border-left:3px solid #007aff;
  border-radius:var(--r);
  overflow:hidden;
  box-shadow:var(--shadow);
  transition:box-shadow 0.3s var(--ease);
}
.cluster:hover{box-shadow:var(--shadow-hover)}
.cluster-head{
  padding:16px;cursor:pointer;
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;
}
.cluster-head .topic{font-size:15px;font-weight:700;flex:1;min-width:200px;color:var(--text)}
.cluster-head .badges{display:flex;gap:6px;flex-wrap:wrap}
.cluster-head .badge{
  font-size:10px;font-weight:600;
  padding:2px 8px;border-radius:10px;
  color:#fff;
}
.cluster-head .meta-line{width:100%;font-size:11px;color:var(--text3);margin-top:2px;font-weight:500}
.cluster-head .arrow{
  font-size:12px;color:var(--text3);
  transition:transform 0.3s var(--ease);
}
.cluster.open .cluster-head .arrow{transform:rotate(180deg)}
.cluster-body{
  max-height:0;overflow:hidden;
  transition:max-height 0.4s var(--ease);
}
.cluster.open .cluster-body{max-height:2000px}
.cluster-body .card{
  margin:0 12px 12px;border-radius:12px;
  box-shadow:none;border:1px solid var(--border);
}
.cluster-body .card:first-child{margin-top:0}

/* ── Category header ── */
.cat-header{
  padding:20px 20px 8px;
  font-size:15px;font-weight:700;
  color:var(--text);
  letter-spacing:-0.2px;
  max-width:960px;margin:0 auto;
}
@media(min-width:960px){.cat-header{max-width:1100px}}
.cat-header span{font-size:12px;color:var(--text3);font-weight:400;margin-left:6px}

/* ── Footer ── */
.footer{
  text-align:center;
  padding:32px 20px 48px;
  font-size:11px;color:var(--text3);
  line-height:2;font-weight:500;
}
.footer a{color:var(--text2);text-decoration:none}
.footer a:hover{text-decoration:underline}

/* ── Empty state ── */
.empty{text-align:center;padding:60px 20px;color:var(--text3);font-size:13px}

/* ── Toast ── */
.toast{
  position:fixed;bottom:32px;left:50%;
  transform:translateX(-50%) translateY(80px);
  background:#1d1d1f;color:#fff;
  border-radius:12px;padding:10px 24px;
  font-size:13px;font-weight:500;
  z-index:200;
  transition:transform 0.35s var(--ease);
  box-shadow:0 8px 24px rgba(0,0,0,0.15);
}
.toast.show{transform:translateX(-50%) translateY(0)}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:0;height:0}
</style>
</head>
<body>

<div class="header">
  <h1>OmniFeed</h1>
  <span class="meta">{{ stats.get('final_items', 0) }} items · {{ generated_at_short }}</span>
  <button class="rfr" onclick="refreshFeed()">Refresh</button>
</div>

<div class="nav" id="nav">
  <div class="nav-item on" data-plat="all" onclick="fp('all',this)">All</div>
  {% for p in platforms %}
  <div class="nav-item" data-plat="{{ p.key }}" onclick="fp('{{ p.key }}',this)">{{ p.label }}</div>
  {% endfor %}
  <div class="nav-item" onclick="showFavs(this)">Saved</div>
</div>

<!-- All -->
<div class="section show" id="view-all">
  <div class="pills" id="catPills">
    <div class="pill on" onclick="fc('all',this)">All</div>
    {% for cat in categories %}
    <div class="pill" onclick="fc('{{ cat }}',this)">{{ cat }}</div>
    {% endfor %}
  </div>
  <div class="grid" id="allGrid">
    {% for item in items %}{{ item.html }}{% endfor %}
  </div>
</div>

<!-- Saved -->
<div class="section" id="view-favs">
  <div class="grid" id="favsGrid"></div>
  <div class="empty" id="favsEmpty">No saved items yet</div>
</div>

<div class="footer">
  {{ stats.get('platforms', 0) }} platforms · {{ stats.get('raw_items', 0) }} fetched · {{ stats.get('final_items', 0) }} curated{% if stats.get('hops',1) > 1 %} · {{ stats.get('hops',1) }}-hop{% endif %}<br>
  {{ generated_at }}
</div>

<div class="toast" id="toast"></div>

<script>
const D=document,Q=s=>D.querySelector(s),QA=s=>D.querySelectorAll(s);
const ALL_ITEMS={{ items_json }};
const ALL_CLUSTERS={{ clusters_json }};
const FK='omnifeed_favs',TK='omnifeed_ix';
let currentPage=0, totalPages=1;

// ── Page-based refresh ──
async function refreshFeed(){
  currentPage++;
  toast('Loading...');
  try{
    const r=await fetch(`page_${currentPage}.json`);
    if(!r.ok){toast('No more pages — run omnifeed fetch');currentPage--;return}
    const newItems=await r.json();
    // Merge into ALL_ITEMS and rebuild grid
    for(const item of newItems){
      if(!ALL_ITEMS.find(i=>i.id===item.id)){
        item.platform_color=(PLAT_COLORS[item.platform]||'#999');
        item.platform_label=(PLAT_LABELS[item.platform]||item.platform);
        ALL_ITEMS.unshift(item);
      }
    }
    // Rebuild the "All" grid
    const grid=Q('#allGrid');
    const newHtml=newItems.map(d=>mkCard(d)).join('');
    grid.innerHTML=newHtml+grid.innerHTML;
    // Re-init fav buttons
    grid.querySelectorAll('.fav').forEach(b=>{if(isFav(b.dataset.id)){b.classList.add('saved');b.textContent='\u2665'}});
    toast(`+${newItems.length} items`);
    Q('.meta').textContent=`${ALL_ITEMS.length} items`;
  }catch(e){toast('Refresh failed');currentPage--}
}

const PLAT_COLORS={{ plat_colors_json }};
const PLAT_LABELS={{ plat_labels_json }};

// ── Favorites ──
function gf(){try{return JSON.parse(localStorage.getItem(FK)||'[]')}catch{return[]}}
function sf(f){localStorage.setItem(FK,JSON.stringify(f))}
function isFav(id){return gf().some(f=>f.id===id)}
function toggleFav(id,el,e){
  e.stopPropagation();
  let f=gf();
  if(isFav(id)){f=f.filter(x=>x.id!==id);el.classList.remove('saved');el.textContent='\u2661';toast('Removed')}
  else{const it=ALL_ITEMS.find(i=>i.id===id);if(it)f.unshift(it);el.classList.add('saved');el.textContent='\u2665';toast('Saved')}
  sf(f);track(id,isFav(id)?'fav':'unfav');
}
D.addEventListener('DOMContentLoaded',()=>{QA('.fav').forEach(b=>{if(isFav(b.dataset.id)){b.classList.add('saved');b.textContent='\u2665'}})});

function renderFavs(){
  const f=gf(),g=Q('#favsGrid'),e=Q('#favsEmpty');
  if(!f.length){g.innerHTML='';e.style.display='block';return}
  e.style.display='none';
  g.innerHTML=f.map(d=>mkCard(d)).join('');
  g.querySelectorAll('.fav').forEach(b=>{b.classList.add('saved');b.textContent='\u2665'});
}

function fixCover(u){if(!u)return '';if(u.startsWith('http://'))return 'https://'+u.slice(7);if(u.startsWith('//'))return 'https:'+u;return u;}
function mkCard(d){
  const coverUrl=fixCover(d.cover);
  const cv=coverUrl?`<img class="cover" src="${coverUrl}" loading="lazy" onerror="this.remove()">`:'';
  const ds=d.content&&d.content!==d.title?`<div class="desc">${d.content.slice(0,120)}</div>`:'';
  const eng=[];
  if(d.engagement){
    if(d.engagement.likes)eng.push(fmtN(d.engagement.likes)+' likes');
    if(d.engagement.views)eng.push(fmtN(d.engagement.views)+' views');
  }
  return `<div class="card" onclick="go('${d.id}','${esc(d.url)}')">
    <button class="fav saved" data-id="${d.id}" onclick="toggleFav('${d.id}',this,event)">\u2665</button>
    ${cv}<div class="body">
    <div class="source" style="color:${d.platform_color}">${d.platform_label}</div>
    <div class="title">${d.title}</div>
    ${ds}
    <div class="author">${d.author}</div>
    <div class="foot">${d.category?`<span class="tag">${d.category}</span>`:''}${eng.map(e=>`<span>${e}</span>`).join('')}${d.date?`<span>${d.date}</span>`:''}</div>
    </div></div>`;
}

// ── Interaction tracking ──
const MAX_IX=200;
function gi(){try{return JSON.parse(localStorage.getItem(TK)||'[]')}catch{return[]}}
function si(a){localStorage.setItem(TK,JSON.stringify(a.slice(-MAX_IX)))}
function track(id,action){
  const it=ALL_ITEMS.find(i=>i.id===id);if(!it)return;
  const l=gi();l.push({id,action,platform:it.platform,category:it.category||'',tags:(it.tags||[]).slice(0,5),ts:Date.now()});si(l);
}
function go(id,url){track(id,'click');window.open(url,'_blank')}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
window.omnifeedExport=function(){
  const l=gi(),pc={},cc={},tc={};let fc=0;
  l.forEach(e=>{if(e.action==='click'||e.action==='fav'){pc[e.platform]=(pc[e.platform]||0)+1;if(e.category)cc[e.category]=(cc[e.category]||0)+1;(e.tags||[]).forEach(t=>{tc[t]=(tc[t]||0)+1})}if(e.action==='fav')fc++});
  return{total:l.length,since:l[0]?.ts?new Date(l[0].ts).toISOString():null,platform_preference:pc,category_preference:cc,tag_affinity:tc,fav_count:fc,raw:l.slice(-50)};
};

function fmtN(n){n=parseInt(n)||0;return n>=10000?(n/10000).toFixed(1)+'w':n>=1000?(n/1000).toFixed(1)+'k':n}

// ── Cluster rendering ──
function mkCluster(cl){
  const items=cl.item_ids.map(id=>ALL_ITEMS.find(i=>i.id===id)).filter(Boolean);
  if(!items.length)return '';
  const badges=cl.platforms.map(p=>`<span class="badge" style="background:${PLAT_COLORS[p]||'#999'}">${PLAT_LABELS[p]||p}</span>`).join('');
  const eng=cl.total_engagement>0?' \u00b7 '+fmtN(cl.total_engagement)+' engagement':'';
  const cards=items.map(d=>mkCardFull(d)).join('');
  return '<div class="cluster" data-cid="'+esc(cl.cluster_id)+'">'
    +'<div class="cluster-head" onclick="this.parentElement.classList.toggle(\'open\')">'
    +'<div class="topic">'+esc(cl.topic)+'</div>'
    +'<div class="badges">'+badges+'</div>'
    +'<span class="arrow">\u25BC</span>'
    +'<div class="meta-line">'+cl.item_count+' items'+eng+'</div>'
    +'</div>'
    +'<div class="cluster-body">'+cards+'</div>'
    +'</div>';
}

// ── View switching ──
function rebuildGrid(items){
  const grid=Q('#allGrid');
  // Identify clustered items
  const clusteredIds=new Set();
  const relevantClusters=[];
  const itemIds=new Set(items.map(i=>i.id));
  ALL_CLUSTERS.forEach(cl=>{
    const inView=cl.item_ids.filter(id=>itemIds.has(id));
    if(inView.length>=2){
      inView.forEach(id=>clusteredIds.add(id));
      relevantClusters.push(Object.assign({},cl,{item_ids:inView,item_count:inView.length}));
    }
  });
  // Render: clusters first, then unclustered items
  let html='';
  relevantClusters.forEach(cl=>{html+=mkCluster(cl)});
  items.filter(d=>!clusteredIds.has(d.id)).forEach(d=>{html+=mkCardFull(d)});
  grid.innerHTML=html;
  grid.querySelectorAll('.fav').forEach(b=>{if(isFav(b.dataset.id)){b.classList.add('saved');b.textContent='\u2665'}});
}
function fp(plat,btn){
  Q('#view-all').classList.add('show');Q('#view-favs').classList.remove('show');
  QA('.nav-item').forEach(t=>t.classList.remove('on'));btn.classList.add('on');
  const pills=QA('#catPills .pill');
  if(pills.length){pills.forEach(b=>b.classList.remove('on'));pills[0].classList.add('on')}
  rebuildGrid(plat==='all'?ALL_ITEMS:ALL_ITEMS.filter(i=>i.platform===plat));
  window.scrollTo(0,0);
}
function fc(cat,btn){
  QA('#catPills .pill').forEach(b=>b.classList.remove('on'));btn.classList.add('on');
  rebuildGrid(cat==='all'?ALL_ITEMS:ALL_ITEMS.filter(i=>(i.category||'')===cat));
}
function mkCardFull(d){
  const coverUrl=fixCover(d.cover);
  const cv=coverUrl?`<img class="cover" src="${coverUrl}" loading="lazy" onerror="this.remove()">`:'';
  const ds=d.content&&d.content!==d.title?`<div class="desc">${esc(d.content).slice(0,120)}</div>`:'';
  const eng=[];
  if(d.engagement){
    if(d.engagement.likes)eng.push(fmtN(d.engagement.likes)+' likes');
    if(d.engagement.views)eng.push(fmtN(d.engagement.views)+' views');
  }
  const pc=PLAT_COLORS[d.platform]||'#999';
  const pl=PLAT_LABELS[d.platform]||d.platform;
  const reason=d.recommend_reason?`<div class="reason">${esc(d.recommend_reason)}</div>`:'';
  const safeUrl=d.url?d.url.replace(/'/g,'%27'):'';
  const safeId=esc(d.id||'');
  return `<div class="card" data-cat="${esc(d.category||'')}" data-plat="${esc(d.platform)}" onclick="go('${safeId}','${safeUrl}')">
    <button class="fav" data-id="${safeId}" onclick="toggleFav('${safeId}',this,event)">\u2661</button>
    ${cv}<div class="body">
    <div class="source" style="color:${pc}">${pl}</div>
    <div class="title">${esc(d.title)}</div>
    ${ds}
    ${d.author?`<div class="author">${esc(d.author)}</div>`:''}
    <div class="foot">${d.category?`<span class="tag">${esc(d.category)}</span>`:''}${eng.map(e=>`<span>${e}</span>`).join('')}${d.date?`<span>${d.date}</span>`:''}</div>
    ${reason}
    </div></div>`;
}
function showFavs(btn){
  Q('#view-all').classList.remove('show');Q('#view-favs').classList.add('show');
  QA('.nav-item').forEach(t=>t.classList.remove('on'));btn.classList.add('on');
  renderFavs();
}
function toast(msg){const t=Q('#toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1600)}
</script>
</body>
</html>'''

HTML_TEMPLATE = Template(HTML_TEMPLATE_STR)


def _fix_cover_url(url: str) -> str:
    """Ensure cover URLs use HTTPS."""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def _make_card_html(d: dict) -> str:
    from html import escape as h
    cover_url = _fix_cover_url(d.get("cover", ""))
    cover = f'<img class="cover" src="{h(cover_url)}" loading="lazy" onerror="this.remove()">' if cover_url else ""
    desc = f'<div class="desc">{h(d["content"][:120])}</div>' if d.get("content") and d["content"] != d["title"] else ""
    reason = f'<div class="reason">{h(d["recommend_reason"])}</div>' if d.get("recommend_reason") else ""
    tag = f'<span class="tag">{h(d["category"])}</span>' if d.get("category") else ""
    date = f'<span>{h(d["date"])}</span>' if d.get("date") else ""

    eng_parts = []
    eng = d.get("engagement", {})
    if eng.get("likes"): eng_parts.append(f'{_fmt(eng["likes"])} likes')
    if eng.get("views"): eng_parts.append(f'{_fmt(eng["views"])} views')
    eng_html = " ".join(f'<span>{p}</span>' for p in eng_parts)

    esc_url = d["url"].replace("'", "%27").replace('"', "%22")
    esc_id = h(d["id"], quote=True)

    return f'''<div class="card" data-cat="{h(d.get("category",""))}" data-plat="{h(d["platform"])}" onclick="go('{esc_id}','{esc_url}')">
<button class="fav" data-id="{esc_id}" onclick="toggleFav('{esc_id}',this,event)">&#x2661;</button>
{cover}<div class="body">
<div class="source" style="color:{d["platform_color"]}">{h(d["platform_label"])}</div>
<div class="title">{h(d["title"])}</div>
{desc}
{f'<div class="author">{h(d["author"])}</div>' if d.get("author") else ''}
<div class="foot">{tag}{eng_html}{date}</div>
{reason}
</div></div>'''


def _fmt(n) -> str:
    try: n = int(n)
    except: return str(n)
    if n >= 10000: return f"{n/10000:.1f}w"
    if n >= 1000: return f"{n/1000:.1f}k"
    return str(n)


def render_html(result: FeedResult, output_path: str) -> str:
    items_data = []
    seen_platforms = set()
    seen_categories = set()
    by_cat = defaultdict(list)

    for item in result.items[:300]:
        pm = PLATFORM_META.get(item.platform, {"label": item.platform, "color": "#999"})
        seen_platforms.add(item.platform)
        if item.category: seen_categories.add(item.category)

        date_str = ""
        if item.timestamp:
            try: date_str = datetime.fromtimestamp(item.timestamp / 1000).strftime("%m-%d %H:%M")
            except: pass

        d = {
            "id": item.id, "platform": item.platform,
            "platform_label": pm["label"], "platform_color": pm["color"],
            "title": item.title or "(untitled)", "content": item.content or "",
            "author": item.author or "", "cover": _fix_cover_url(item.cover or ""),
            "url": item.url or "#", "category": item.category or "",
            "tags": item.tags[:5] if item.tags else [],
            "engagement": {"likes": item.engagement.likes, "comments": item.engagement.comments, "views": item.engagement.views},
            "recommend_reason": item.recommend_reason or "", "date": date_str,
            "cluster_id": item.cluster_id or "",
        }
        d["html"] = _make_card_html(d)
        items_data.append(d)
        if item.category: by_cat[item.category].append(d)

    items_json = [{k: v for k, v in d.items() if k != "html"} for d in items_data]

    platforms = [{"key": p, "label": PLATFORM_META.get(p, {}).get("label", p)}
                 for p in sorted(seen_platforms)]

    generated_short = result.generated_at[:16] if result.generated_at else ""

    plat_colors = {k: v["color"] for k, v in PLATFORM_META.items()}
    plat_labels = {k: v["label"] for k, v in PLATFORM_META.items()}

    # Build cluster data for template
    clusters_json = []
    if result.clusters:
        for c in result.clusters:
            cluster_item_ids = [it.id for it in c.items]
            cluster_platforms = c.platforms
            clusters_json.append({
                "cluster_id": c.cluster_id,
                "topic": c.topic,
                "platforms": cluster_platforms,
                "item_count": len(c.items),
                "total_engagement": int(c.total_engagement),
                "item_ids": cluster_item_ids,
            })

    html = HTML_TEMPLATE.render(
        stats=result.stats,
        generated_at=result.generated_at,
        generated_at_short=generated_short,
        items=items_data,
        items_json=json.dumps(items_json, ensure_ascii=False),
        plat_colors_json=json.dumps(plat_colors, ensure_ascii=False),
        plat_labels_json=json.dumps(plat_labels, ensure_ascii=False),
        clusters_json=json.dumps(clusters_json, ensure_ascii=False),
        platforms=platforms,
        categories=sorted(seen_categories),
        by_cat=dict(by_cat),
    )

    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    # PWA manifest
    manifest = {
        "name": "OmniFeed", "short_name": "OmniFeed",
        "start_url": ".", "display": "standalone",
        "background_color": "#f5f5f7", "theme_color": "#ffffff",
        "icons": [{"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>O</text></svg>", "sizes": "any", "type": "image/svg+xml"}],
    }
    (out.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return str(out)


def render_json(result: FeedResult, output_path: str) -> str:
    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.to_json(indent=2), encoding="utf-8")
    return str(out)


def render_digest(result: FeedResult) -> str:
    lines = [f"OmniFeed Daily — {result.generated_at[:10] if result.generated_at else 'today'}\n"]
    by_cat: dict[str, list] = defaultdict(list)
    for item in result.items[:30]:
        by_cat[item.category or "Other"].append(item)
    for cat in sorted(by_cat.keys()):
        lines.append(f"\n## {cat}")
        for i, item in enumerate(by_cat[cat][:5], 1):
            pm = PLATFORM_META.get(item.platform, {"label": item.platform})
            eng = f" ({item.engagement.likes} likes)" if item.engagement.likes else ""
            lines.append(f"{i}. [{pm['label']}] {item.title}{eng}")
            if item.content and item.content != item.title:
                lines.append(f"   {(item.summary or item.content)[:80]}")
            if item.url: lines.append(f"   {item.url}")
    stats = result.stats
    lines.append(f"\n---\n{stats.get('platforms',0)} platforms · {stats.get('raw_items',0)} raw → {stats.get('final_items',0)} curated")
    return "\n".join(lines)
