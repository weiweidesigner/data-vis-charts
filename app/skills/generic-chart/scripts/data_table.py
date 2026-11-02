#!/usr/bin/env python3
"""Standalone complete-data table with local file handoff and virtual scrolling."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def field_value(record, field):
    value=record
    for key in field if isinstance(field,list) else field.split('.'):
        if not isinstance(value,dict) or key not in value: raise ValueError(f'Missing mapped field {field!r}')
        value=value[key]
    return value


def safe_link(value):
    if not isinstance(value,str) or any(ord(c)<33 for c in value) or '\\' in value:return None
    try:
        url=urlsplit(value)
        return value if url.scheme=='https' and url.hostname and url.username is None and url.password is None else None
    except ValueError:return None


def resolve_links(rows,columns,base):
    links=[[None for _ in columns] for _ in rows];cache={};sources=[];coverage=[]
    for col,c in enumerate(columns):
        spec=c.get('link')
        if not spec:continue
        if not isinstance(spec,dict) or bool(spec.get('urlField'))==bool(spec.get('lookup')):raise ValueError('link requires exactly one of urlField or lookup')
        catalog=None
        if spec.get('lookup'):
            lookup=spec['lookup']
            if not isinstance(lookup,dict):raise ValueError('link.lookup must be an object')
            identity=json.dumps(lookup,sort_keys=True)
            if identity not in cache:
                name=lookup.get('path')
                if not isinstance(name,str) or not name or '://' in name:raise ValueError('link.lookup.path must be a local verified URL catalog')
                path=Path(name).expanduser();path=path if path.is_absolute() else base/path
                raw=path.read_bytes();items=json.loads(raw.decode('utf-8-sig'))
                keys=lookup.get('recordsPath',[])
                if not isinstance(keys,list):raise ValueError('lookup recordsPath must be an array')
                for key in keys:items=items[key]
                if not isinstance(items,list):raise ValueError('link catalog must select an array')
                where=lookup.get('where',{})
                if not isinstance(where,dict):raise ValueError('link lookup where must be exact field/value filters')
                found={}
                for item in items:
                    if not isinstance(item,dict):continue
                    if any(field_value(item,k)!=v for k,v in where.items()):continue
                    key=field_value(item,lookup['keyField']);url=safe_link(field_value(item,lookup['urlField']))
                    if key is not None and url:found.setdefault(str(key).strip().casefold(),set()).add(url)
                # Ambiguous identities remain plain text; never select an arbitrary exchange.
                cache[identity]={key:next(iter(urls)) for key,urls in found.items() if len(urls)==1}
                sources.append({'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest()})
            catalog=cache[identity]
        for i,row in enumerate(rows):
            try:
                url=safe_link(field_value(row,spec['urlField'])) if catalog is None else catalog.get(str(field_value(row,spec.get('keyField',c['field']))).strip().casefold())
            except ValueError as exc:raise ValueError(f'Row {i+1} link: {exc}') from None
            links[i][col]=url
        count=sum(bool(row[col]) for row in links);coverage.append({'field':c['field'],'linkedRows':count,'unlinkedRows':len(rows)-count})
    return links,sources,coverage


def normalize(payload, base=None):
    if not isinstance(payload,dict):raise ValueError('Table payload must be an object')
    source=payload.get('dataSource');rows=payload.get('rows');provenance=None
    if source is not None:
        if rows is not None or not isinstance(source,dict):raise ValueError('Use dataSource or rows, not both')
        name=source.get('path')
        if not isinstance(name,str) or not name or '://' in name:raise ValueError('dataSource.path must be a local JSON file')
        path=Path(name).expanduser();path=path if path.is_absolute() else (base or Path.cwd())/path
        raw=path.read_bytes();rows=json.loads(raw.decode('utf-8-sig'));keys=source.get('recordsPath',[])
        if not isinstance(keys,list):raise ValueError('recordsPath must be an array')
        for key in keys:rows=rows[key]
        provenance={'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'recordsPath':keys}
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Table rows must be an array of records')
    columns=payload.get('columns')
    if not isinstance(columns,list) or not columns:raise ValueError('Specify nonempty columns with exact field mappings')
    normalized=[];seen=set()
    for c in columns:
        if not isinstance(c,dict):raise ValueError('Column must be an object')
        field=c.get('field');valid=isinstance(field,str) and bool(field) or isinstance(field,list) and bool(field) and all(isinstance(k,str) for k in field)
        if not valid:raise ValueError('Column field must be a path string or nonempty key array')
        identity=json.dumps(field)
        if identity in seen:raise ValueError('Duplicate table column field')
        seen.add(identity);kind=c.get('type','text')
        if kind not in ('text','number','percent','date'):raise ValueError('Unsupported table column type')
        role=c.get('role','data')
        if role not in ('data','index','change'):raise ValueError('Column role must be data, index or change')
        if role=='change' and kind not in ('number','percent'):raise ValueError('Change semantics require a numeric column')
        align=c.get('align','left' if role=='index' else 'right' if kind in ('number','percent') else 'left')
        if align not in ('left','right','center'):raise ValueError('Invalid column alignment')
        width=c.get('width',40 if role=='index' else 140 if kind in ('number','percent') else 200)
        if isinstance(width,bool) or not isinstance(width,int) or not (28 if role=='index' else 80)<=width<=(80 if role=='index' else 640):raise ValueError('Index width must be 28..80 pixels; other columns 80..640')
        digits=c.get('digits')
        if digits is not None and (isinstance(digits,bool) or not isinstance(digits,int) or not 0<=digits<=12):raise ValueError('digits must be 0..12')
        normalized.append({'field':field,'label':str(c.get('label') or (field[-1] if isinstance(field,list) else field)),
                           'type':kind,'role':role,'link':c.get('link'),'align':align,'width':width,'digits':digits,'prefix':str(c.get('prefix') or ''),'suffix':str(c.get('suffix') or '')})
    market=payload.get('financialMarket')
    if market is not None and market not in ('US','CN','HK','international'):raise ValueError('financialMarket must be US, CN, HK or international')
    if any(c['role']=='change' for c in normalized) and market is None:raise ValueError('Change colors require explicit financialMarket; language does not select market conventions')
    links,link_sources,link_coverage=resolve_links(rows,normalized,base or Path.cwd())
    values=[]
    for i,row in enumerate(rows):
        try:values.append([field_value(row,c['field']) for c in normalized])
        except ValueError as exc:raise ValueError(f'Row {i+1}: {exc}') from None
    height=payload.get('height',360)
    if isinstance(height,bool) or not isinstance(height,int) or not 180<=height<=1000:raise ValueError('height must be 180..1000 pixels')
    theme=payload.get('theme',payload.get('themeMode','light'))
    if theme not in ('dark','light'):raise ValueError('theme must be light or dark')
    title=str(payload.get('title') or '')
    locale=payload.get('locale') or ('zh-CN' if re.search(r'[\u3400-\u9fff]',title+''.join(c['label'] for c in normalized)) else 'en-US')
    if not isinstance(locale,str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',locale):raise ValueError('locale must be a BCP47 language tag')
    if provenance:provenance.update(recordCount=len(rows),fields=[c['field'] for c in normalized])
    return {'type':'data-table','title':title,'locale':locale,'theme':theme,'height':height,'columns':normalized,'rows':values,'fileSource':provenance,'financialMarket':market,'links':links,'linkSources':link_sources,'linkCoverage':link_coverage}


def build_html(config):
    data=json.dumps(config,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('&','\\u0026')
    title=html.escape(config['title'] or 'Data table')
    license=(Path(__file__).resolve().parents[1]/'runtime/lucide-LICENSE.txt').read_text()
    document=TEMPLATE.replace('__LICENSE__',license).replace('__TITLE__',title).replace('__THEME__',config['theme']).replace('__DATA__',data)
    return document


TEMPLATE=r'''<!doctype html><html lang="en" data-theme="__THEME__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><!-- __LICENSE__ -->
<style>
:root{--gain:#089981;--loss:#f23645;--bg:#fff;--text:#171b22;--muted:#737780;--line:#e8eaed;--hover:#f5f6f8;--focus:#6278d8;--shadow:0 10px 35px #0002;color-scheme:light}html[data-theme=dark]{--gain:#26a69a;--loss:#ef5350;--bg:#101010;--text:#eee;--muted:#a0a0a0;--line:#303030;--hover:#202020;--focus:#a2aaff;--shadow:0 10px 35px #0008;color-scheme:dark}
*{box-sizing:border-box}html,body{margin:0;width:100%;background:transparent;color:var(--text);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}button{font:inherit;color:inherit}button:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}
.data-table-component{width:100%;min-width:0;background:transparent;display:flex;flex-direction:column;gap:8px}.table-toolbar{display:flex;align-items:center;gap:12px;min-height:32px}.table-title{font-size:16px;font-weight:650;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}.fullscreen-button{margin-left:auto}.table-control{display:inline-flex;align-items:center;justify-content:center;flex:0 0 28px;width:28px;height:28px;background:transparent;border:1px solid var(--line);border-radius:6px;cursor:pointer}.table-control:hover{background:var(--hover)}svg.lucide{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;display:block}
.table-viewport{width:100%;min-height:0;overflow:auto;overscroll-behavior:contain;touch-action:pan-x pan-y;position:relative;border-top:1px solid var(--line);scrollbar-gutter:stable;isolation:isolate}table{border-collapse:separate;border-spacing:0;table-layout:fixed;min-width:100%;font-size:13px}th,td{padding:0 12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;height:44px;max-height:44px;box-sizing:border-box}th{position:sticky;top:0;z-index:2;background:var(--bg);color:var(--muted);font-weight:500;font-size:12px;border-bottom:1px solid var(--line);height:40px}td{border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}tbody tr[data-row-index]:hover td{background:var(--hover)}.cell-value{display:block;width:100%;height:43px;line-height:43px;border:0;background:transparent;text-align:inherit;padding:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:text;font-variant-numeric:tabular-nums}.head-button{width:100%;height:39px;display:flex;align-items:center;gap:6px;border:0;padding:0;background:transparent;text-align:inherit;cursor:pointer}.head-button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.head-button:hover{color:var(--text)}th[aria-sort=ascending] .head-button,th[aria-sort=descending] .head-button{color:#3b82f6}.head-button svg{width:12px;height:12px;flex:none}th[data-align=right] .head-button{justify-content:flex-end}th[data-align=center] .head-button{justify-content:center}.spacer td{padding:0;border:0;height:0;font-size:0;line-height:0}.empty-cell{height:100px;text-align:center;color:var(--muted)}.table-error{color:var(--muted);font-size:12px}.data-table-component:fullscreen,.data-table-component:-webkit-full-screen{background:var(--bg);width:100vw;height:100dvh;max-height:none;padding:16px;gap:10px}.data-table-component:fullscreen .table-viewport,.data-table-component:-webkit-full-screen .table-viewport{flex:1;height:auto!important}.data-table-component:fullscreen .table-toolbar{flex:none}
@media(max-width:600px){.table-title{font-size:14px}.table-toolbar{gap:8px}.data-table-component:fullscreen{padding:10px}}
.data-table-component{--price-up:var(--gain);--price-down:var(--loss)}.data-table-component[data-financial-market=CN],.data-table-component[data-financial-market=HK]{--price-up:var(--loss);--price-down:var(--gain)}
th[data-role=index],td[data-role=index]{padding-left:4px;padding-right:4px}td[data-role=index]{color:var(--muted);font-size:11px;font-weight:400}td[data-change=up]{color:var(--price-up)}td[data-change=down]{color:var(--price-down)}td[data-change=neutral]{color:var(--muted)}a.cell-link{color:inherit;text-decoration:none;cursor:pointer}a.cell-link:hover,a.cell-link:focus-visible{text-decoration-line:underline;text-decoration-style:dashed;text-underline-offset:4px;text-decoration-thickness:1px}
</style></head><body><section class="data-table-component" data-data-table-version="5">
<div class="table-toolbar"><h2 class="table-title"></h2><button class="table-control fullscreen-button" type="button"></button></div>
<div class="table-viewport" tabindex="0"><table><colgroup></colgroup><thead><tr></tr></thead><tbody></tbody></table></div><div class="table-error" role="status" hidden></div>
</section><script id="table-data" type="application/json">__DATA__</script><script>
(()=>{'use strict';
const config=JSON.parse(document.getElementById('table-data').textContent),root=document.querySelector('.data-table-component'),viewport=root.querySelector('.table-viewport'),table=root.querySelector('table'),body=table.tBodies[0],head=table.tHead.rows[0],full=root.querySelector('.fullscreen-button'),error=root.querySelector('.table-error');
const zh=/^zh/i.test(config.locale),t=(en,cn)=>zh?cn:en,ROW=44,OVERSCAN=8;
document.documentElement.lang=config.locale;root.dataset.financialMarket=config.financialMarket||'';root.querySelector('.table-title').textContent=config.title;root.querySelector('.table-title').title=config.title;table.setAttribute('aria-label',config.title||t('Data table','数据表格'));table.setAttribute('aria-rowcount',config.rows.length+1);table.setAttribute('aria-colcount',config.columns.length);viewport.setAttribute('aria-label',t('Scrollable table','可滚动表格'));
const paths={maximize:'<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',minimize:'<path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"/>',ascending:'<path d="m5 12 7-7 7 7M12 19V5"/>',descending:'<path d="m5 12 7 7 7-7M12 5v14"/>',close:'<path d="m18 6-12 12M6 6l12 12"/>'};
const icon=name=>'<svg class="lucide lucide-'+name+'" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'+paths[name]+'</svg>';
let order=config.rows.map((_,i)=>i),sortColumn=-1,sortDirection=0,scheduled=false;
const nf=new Map(),collator=new Intl.Collator(config.locale,{numeric:true,sensitivity:'base'});
const numeric=v=>v!==null&&v!==''&&typeof v!=='boolean'&&Number.isFinite(Number(v));
function rawText(v){return v===null?'—':typeof v==='object'?JSON.stringify(v,null,2):String(v)}
function format(v,c){if(v===null)return'—';let text;if((c.type==='number'||c.type==='percent')&&numeric(v)){const key=String(c.digits);if(!nf.has(key))nf.set(key,new Intl.NumberFormat(config.locale,c.digits==null?{maximumFractionDigits:6}:{minimumFractionDigits:c.digits,maximumFractionDigits:c.digits}));text=nf.get(key).format(Number(v));if(c.type==='percent')text+='%'}else{text=rawText(v);if(c.type==='date'){if(/^\d{8}$/.test(text))text=text.slice(0,4)+'-'+text.slice(4,6)+'-'+text.slice(6);else text=text.replace(/^(\d{4}-\d{2}-\d{2})T/,'$1 ')}}return c.prefix+text+c.suffix}
function sort(index){sortDirection=sortColumn===index&&sortDirection===-1?1:-1;sortColumn=index;order=config.rows.map((_,i)=>i);const c=config.columns[index];if(sortDirection)order.sort((a,b)=>{const x=config.rows[a][index],y=config.rows[b][index];if(x===null||y===null)return x===y?a-b:x===null?1:-1;const delta=(c.type==='number'||c.type==='percent')&&numeric(x)&&numeric(y)?Number(x)-Number(y):collator.compare(rawText(x),rawText(y));return delta?delta*sortDirection:a-b});[...head.cells].forEach((th,i)=>{const active=i===sortColumn,direction=sortDirection===1?'ascending':'descending';th.setAttribute('aria-sort',active?direction:'none');th.querySelector('svg')?.remove();if(active)th.querySelector('button').insertAdjacentHTML('beforeend',icon(direction));});viewport.scrollTop=0;render()}
config.columns.forEach((c,i)=>{const col=document.createElement('col');col.style.width=c.width+'px';table.querySelector('colgroup').append(col);const th=document.createElement('th');th.scope='col';th.dataset.role=c.role||'data';th.style.textAlign=c.align;th.dataset.align=c.align;th.setAttribute('aria-sort','none');if(c.role==='index'){th.setAttribute('aria-label',c.label||t('Row number','序号'));head.append(th);return;}const b=document.createElement('button');b.type='button';b.className='head-button';const label=document.createElement('span');label.textContent=c.label;b.append(label);b.title=t('Sort: ','排序：')+c.label;b.onclick=()=>sort(i);th.append(b);head.append(th)});
function spacer(height){const tr=document.createElement('tr');tr.className='spacer';tr.setAttribute('aria-hidden','true');const td=document.createElement('td');td.colSpan=config.columns.length;td.style.height=height+'px';tr.append(td);return tr}
function render(){scheduled=false;const n=order.length,start=Math.min(n,Math.max(0,Math.floor(viewport.scrollTop/ROW)-OVERSCAN)),end=Math.min(n,Math.ceil((viewport.scrollTop+viewport.clientHeight)/ROW)+OVERSCAN),fragment=document.createDocumentFragment();if(!n){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=config.columns.length;td.className='empty-cell';td.textContent=t('No data','暂无数据');tr.append(td);fragment.append(tr)}else{fragment.append(spacer(start*ROW));for(let pos=start;pos<end;pos++){const row=order[pos],tr=document.createElement('tr');tr.dataset.rowIndex=row;tr.setAttribute('aria-rowindex',pos+2);config.columns.forEach((c,col)=>{const td=document.createElement('td');td.style.textAlign=c.align;td.dataset.role=c.role||'data';if(c.role==='change'){const v=config.rows[row][col];td.dataset.change=numeric(v)&&Number(v)!==0?(Number(v)>0?'up':'down'):'neutral';}const url=config.links?.[row]?.[col];const button=document.createElement(url?'a':'span');button.className='cell-value'+(url?' cell-link':'');if(url){button.href=url;button.target='_blank';button.rel='noopener noreferrer';}button.textContent=format(config.rows[row][col],c);button.title=rawText(config.rows[row][col]);td.append(button);tr.append(td)});fragment.append(tr)}fragment.append(spacer((n-end)*ROW))}body.replaceChildren(fragment);}
function resize(){const total=config.columns.reduce((sum,c)=>sum+c.width,0),flex=config.columns.reduce((sum,c)=>sum+(c.role==='index'?0:c.width),0),extra=Math.max(0,viewport.clientWidth-total);[...table.querySelector('colgroup').children].forEach((col,i)=>{const c=config.columns[i];col.style.width=(c.width+(c.role==='index'||!flex?0:extra*c.width/flex))+'px'});table.style.width=Math.max(viewport.clientWidth,total)+'px';render();if(!document.fullscreenElement)parent.postMessage({type:'analysis-planner-report-height',height:Math.ceil(root.getBoundingClientRect().height)},'*')}
viewport.style.height=Math.min(config.height,config.rows.length?config.rows.length*ROW+40:140)+'px';
viewport.addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(render)}},{passive:true});
function fullscreenChanged(){const active=document.fullscreenElement===root||document.webkitFullscreenElement===root;full.innerHTML=icon(active?'minimize':'maximize');full.title=full.ariaLabel=active?t('Exit fullscreen','退出全屏'):t('Fullscreen','全屏查看');requestAnimationFrame(resize)}
full.onclick=async()=>{try{if(document.fullscreenElement||document.webkitFullscreenElement){if(document.exitFullscreen)await document.exitFullscreen();else document.webkitExitFullscreen()}else{if(root.requestFullscreen)await root.requestFullscreen();else if(root.webkitRequestFullscreen)root.webkitRequestFullscreen();else throw new Error('unsupported')}}catch{error.hidden=false;error.textContent=t('Fullscreen is unavailable in this environment','当前环境不支持全屏查看')}};
document.addEventListener('fullscreenchange',fullscreenChanged);document.addEventListener('webkitfullscreenchange',fullscreenChanged);new ResizeObserver(resize).observe(viewport);window.addEventListener('message',e=>{if(e.source!==parent)return;const theme=e.data?.theme||e.data?.value;if(['dark','light'].includes(theme))document.documentElement.dataset.theme=theme});fullscreenChanged();resize();
})();</script></body></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema',action='store_true');parser.add_argument('--payload');parser.add_argument('--data-json');parser.add_argument('--output');parser.add_argument('--payload-output');parser.add_argument('--title');parser.add_argument('--theme',choices=['light','dark'])
    args=parser.parse_args()
    if args.schema:
        print((Path(__file__).resolve().parents[1]/'schemas/data_table.schema.json').read_text());return
    if not args.output or bool(args.payload)==bool(args.data_json):parser.error('Provide --output and exactly one of --payload or --data-json')
    payload=json.loads(Path(args.payload).expanduser().read_text()) if args.payload else json.loads(args.data_json)
    if args.title:payload['title']=args.title
    if args.theme:payload['theme']=args.theme
    config=normalize(payload);out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(build_html(config),encoding='utf-8')
    if args.payload_output:
        p=Path(args.payload_output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(config,ensure_ascii=False,allow_nan=False,indent=2))
    presentation={'kind':'table','status':'rendered','artifact':str(out.resolve()),'coveredFields':[c['field'] for c in config['columns']],
                  'scope':{'rowCount':len(config['rows']),'columnCount':len(config['columns']),'sourceCoverage':'all-input-records-only','fileSource':config['fileSource'],'linkCoverage':config['linkCoverage'],'linkSources':config['linkSources'],'financialMarket':config['financialMarket']},
                  'markdownPolicy':'The table component already presents these input records and selected fields. Do not repeat them as a Markdown table, row-by-row list or duplicate title. Add conclusions, comparisons and material limitations in prose. Honor an explicit user request for Markdown or plain text.'}
    print(json.dumps({'ok':True,'output':str(out.resolve()),'chartName':'data_table','rowCount':len(config['rows']),'columnCount':len(config['columns']),'fileSource':config['fileSource'],'presentation':presentation},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except (ValueError,TypeError,KeyError,OSError) as exc:raise SystemExit(str(exc)) from None
