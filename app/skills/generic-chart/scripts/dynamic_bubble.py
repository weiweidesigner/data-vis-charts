#!/usr/bin/env python3
"""Standalone dynamic bubble chart renderer with inline styles."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


def parse_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload:
        raw = json.loads(Path(args.payload).expanduser().read_text(encoding="utf-8"))
    elif args.data_json:
        raw = parse_json(args.data_json)
    else:
        raw = {}
    payload = normalize_payload(raw)
    if args.data:
        payload["data"] = parse_json(args.data)
    if args.title:
        payload["title"] = args.title
    return payload


def normalize_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("chartPayload"), dict):
        payload = dict(raw["chartPayload"])
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        payload = {"data": raw}
    if not isinstance(payload.get("encode"), dict):
        encode: dict[str, Any] = {}
        field_aliases = {
            "time": ("timeField", "frameField"),
            "x": ("xField",),
            "y": ("yField",),
            "size": ("sizeField",),
            "name": ("nameField", "labelField"),
            "color": ("colorField", "groupField", "seriesField"),
        }
        for channel, keys in field_aliases.items():
            for key in keys:
                if payload.get(key):
                    encode[channel] = payload[key]
                    break
        if encode:
            payload["encode"] = encode
    return payload


def rows_of(data: Any) -> list[dict[str, Any]]:
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def is_number(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and value not in (None, "") and float(str(value).replace(",", "")) == float(str(value).replace(",", ""))
    except ValueError:
        return False


def infer_encode(payload: dict[str, Any]) -> dict[str, str]:
    rows = rows_of(payload.get("data"))
    encode = payload.get("encode") if isinstance(payload.get("encode"), dict) else {}
    keys = list(rows[0].keys()) if rows else []
    lower = {key.lower(): key for key in keys}
    time = encode.get("time") or lower.get("time") or lower.get("date") or lower.get("year") or lower.get("frame")
    x = encode.get("x") or lower.get("x") or lower.get("value") or lower.get("amount")
    y = encode.get("y") or lower.get("y") or lower.get("rate") or lower.get("growth")
    size = encode.get("size") or lower.get("size") or lower.get("volume") or lower.get("marketcap") or lower.get("count")
    name = encode.get("name") or lower.get("name") or lower.get("label") or lower.get("category")
    series = encode.get("color") or encode.get("series") or lower.get("color") or lower.get("series") or lower.get("group")
    numeric = [key for key in keys if key != time and is_number(rows[0].get(key))]
    text = [key for key in keys if key not in numeric]
    x = x or (numeric[0] if numeric else "x")
    y = y or (numeric[1] if len(numeric) > 1 else x)
    size = size or (numeric[2] if len(numeric) > 2 else y)
    name = name or next((key for key in text if key != time and key != series), text[0] if text else x)
    series = series or "__series"
    for row in rows:
        row.setdefault(series, payload.get("title") or "Series")
    result = {"x": str(x), "y": str(y), "size": str(size), "name": str(name), "series": str(series)}
    if time:
        result["time"] = str(time)
    return result


FIELD_LABELS = {
    "year": "年份",
    "time": "时间",
    "date": "日期",
    "country": "国家",
    "continent": "洲别",
    "region": "地区",
    "life_expectancy": "预期寿命",
    "gdp_per_capita": "人均GDP",
    "gdp": "GDP",
    "population": "人口",
    "market_cap": "市值",
    "marketcap": "市值",
    "revenue": "营收",
    "profit": "利润",
    "growth": "增长率",
    "volume": "成交量",
    "count": "数量",
    "size": "规模",
}


def humanize_field(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    key = text.lower()
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    text = re.sub(r"[_\-]+", " ", text).strip()
    return text[:1].upper() + text[1:] if text else ""


def infer_title(rows: list[dict[str, Any]], encode: dict[str, str], labels: dict[str, str]) -> str:
    x_label = labels.get("x") or humanize_field(encode.get("x"))
    y_label = labels.get("y") or humanize_field(encode.get("y"))
    name_field = str(encode.get("name") or "").lower()

    if x_label and y_label:
        prefix = "全球各国" if name_field in {"country", "国家"} else ""
        base = f"{prefix}{y_label}与{x_label}变化"

        time_field = encode.get("time")
        if time_field:
            values = [row.get(time_field) for row in rows if row.get(time_field) not in (None, "")]
            if values:
                def sort_key(value: Any) -> tuple[int, Any]:
                    try:
                        return (0, float(value))
                    except (TypeError, ValueError):
                        return (1, str(value))

                ordered = sorted({str(value) for value in values}, key=sort_key)
                if ordered:
                    period = ordered[0] if len(ordered) == 1 else f"{ordered[0]}–{ordered[-1]}"
                    return f"{base}（{period}）"
        return base

    return "动态气泡图"

def build_html(payload: dict[str, Any]) -> str:
    rows = rows_of(payload.get("data"))
    encode = infer_encode(payload)
    labels = {
        "x": str(payload.get("xLabel") or payload.get("xAxisLabel") or humanize_field(encode.get("x")) or "X"),
        "y": str(payload.get("yLabel") or payload.get("yAxisLabel") or humanize_field(encode.get("y")) or "Y"),
        "size": str(payload.get("sizeLabel") or payload.get("valueLabel") or humanize_field(encode.get("size")) or "规模"),
        "time": str(payload.get("timeLabel") or humanize_field(encode.get("time")) or "时间"),
    }
    title = str(payload.get("title") or infer_title(rows, encode, labels))
    safe_title = html.escape(title)
    data_json = json.dumps({"rows": rows, "encode": encode, "labels": labels}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{safe_title}</title>
<script src="/static/vendor/echarts.min.js"></script>
<script>window.echarts||document.write('<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"><\\/script>')</script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;width:100%;height:auto;min-height:0;background:transparent;color:#151922;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}}
#wrap{{position:relative;width:100%;height:clamp(400px,32vw,520px);min-height:400px;max-height:520px;background:transparent;border:0;overflow:hidden;--grid-left:0px;--grid-right:1px}}
#header{{position:absolute;left:0!important;right:12px;top:14px;z-index:6;margin:0!important;padding:0!important;transform:none!important}}
#title{{position:relative!important;left:0!important;right:auto!important;top:auto!important;margin:0!important;padding:0!important;transform:none!important;font-family:"PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;font-size:22px;line-height:1.35;font-weight:700;letter-spacing:-.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#151922}}
#legend{{display:flex;align-items:center;flex-wrap:wrap;gap:8px 20px;margin:12px 0 0!important;padding:0!important;min-height:18px}}
.legendItem{{display:inline-flex;align-items:center;gap:7px;margin:0;padding:0;color:#687386;font-size:12px;line-height:18px;white-space:nowrap}}
.legendDot{{width:9px;height:9px;flex:0 0 9px;border-radius:50%}}
#chart{{position:absolute;inset:0;height:100%;min-height:100%}}
#empty{{display:none;position:absolute;inset:0;align-items:center;justify-content:center;color:#687386;font-size:14px;z-index:4}}
#timelineBar{{position:absolute;left:0;right:0;bottom:14px;z-index:5;display:flex;align-items:center;gap:8px;padding:6px 0 6px 8px;border-radius:999px;background:transparent;border:1px solid transparent;box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none}}
#timelineBar.is-hidden{{display:none}}
#playBtn{{width:28px;height:28px;position:relative;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;padding:0;border:0;border-radius:999px;background:#4c91ff;color:#fff;cursor:pointer;box-shadow:none}}
#playBtn::before{{content:"";width:0;height:0;border-top:4px solid transparent;border-bottom:4px solid transparent;border-left:6px solid #fff;transform:translateX(1px)}}
#playBtn.is-playing::before{{width:8px;height:10px;border:0;border-radius:1px;background:linear-gradient(90deg,#fff 0 36%,transparent 36% 64%,#fff 64% 100%);transform:none}}
.timeLabel{{min-width:58px;color:#687386;font-size:12px;line-height:1;text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}}
#endLabel{{position:absolute;right:0;top:50%;min-width:auto;transform:translateY(-50%);text-align:right;pointer-events:none}}
#sliderWrap{{position:relative;display:flex;align-items:center;flex:1;min-width:80px;height:28px;padding:0;--end-label-space:0px}}
#sliderTrack{{position:absolute;left:0;right:var(--end-label-space);top:50%;height:4px;border-radius:999px;background:rgba(76,145,255,.16);transform:translateY(-50%);pointer-events:none;overflow:hidden}}
#sliderFill{{display:block;width:0;height:100%;border-radius:inherit;background:#4c91ff}}
#timelineRange{{position:absolute;left:0;right:var(--end-label-space);top:0;bottom:0;width:auto;height:28px;margin:0;appearance:none;background:transparent;cursor:pointer;z-index:2}}
#timelineRange::-webkit-slider-thumb{{appearance:none;width:14px;height:14px;margin-top:-5px;border-radius:999px;background:#4c91ff;border:0;box-shadow:0 0 0 5px rgba(76,145,255,.14)}}
#timelineRange::-webkit-slider-runnable-track{{height:4px;background:transparent}}
#timelineRange::-moz-range-thumb{{width:14px;height:14px;border-radius:999px;background:#4c91ff;border:0;box-shadow:0 0 0 5px rgba(76,145,255,.14)}}
#timelineRange::-moz-range-track{{height:4px;background:transparent}}
#speedBtn{{height:28px;min-height:28px;line-height:28px;min-width:42px;padding:0 10px;border-radius:999px;border:1px solid transparent;background:rgba(148,163,184,.10);color:#151922;font-size:12px;font-weight:750;cursor:pointer}}
@media(min-width:721px) and (max-width:1100px){{
 #wrap{{height:clamp(380px,40vw,460px);min-height:380px;max-height:460px}}
}}
@media(max-width:720px){{
 html,body{{height:auto;min-height:0}}
 #wrap{{height:clamp(300px,78vw,360px);min-height:300px;max-height:360px;--grid-left:0px;--grid-right:1px}}
 #header{{right:8px;top:10px}}
 #title{{font-size:17px;font-weight:700;letter-spacing:0}}
 #legend{{gap:6px 12px;margin-top:8px!important}}
 .legendItem{{font-size:11px;gap:6px}}
 #timelineBar{{left:0;right:0;bottom:12px;gap:7px;padding:5px 0 5px 8px;border-radius:999px}}
 .timeLabel{{min-width:42px;font-size:11px}}
 #speedBtn{{height:28px;min-height:28px;line-height:28px;min-width:38px;padding:0 9px}}
}}
</style></head><body><div id="wrap" data-renderer-version="dynamic-bubble-v15"><div id="header"><div id="title">{safe_title}</div><div id="legend"></div></div><div id="chart"></div><div id="empty">暂无可渲染数据</div><div id="timelineBar" class="is-hidden"><button id="playBtn" type="button" aria-label="播放"></button><button id="speedBtn" type="button">1x</button><div id="startLabel" class="timeLabel"></div><div id="sliderWrap"><div id="sliderTrack"><span id="sliderFill"></span></div><input id="timelineRange" type="range" min="0" max="0" value="0" aria-label="时间轴" /></div><div id="endLabel" class="timeLabel"></div></div></div>
<script>
const payload={data_json};
const rows=payload.rows||[], enc=payload.encode||{{}}, labels=payload.labels||{{}};
const palette=["#38bdf8","#34d399","#f97316","#a78bfa","#f43f5e","#facc15","#fb7185","#2dd4bf"];
const empty=document.getElementById("empty");
const titleEl=document.getElementById("title");
const legendEl=document.getElementById("legend");
const timelineBar=document.getElementById("timelineBar");
const playBtn=document.getElementById("playBtn");
const speedBtn=document.getElementById("speedBtn");
const range=document.getElementById("timelineRange");
const sliderFill=document.getElementById("sliderFill");
const startLabel=document.getElementById("startLabel");
const endLabel=document.getElementById("endLabel");
const chart=echarts.init(document.getElementById("chart"));
const speedPresets=[{{label:"1x",interval:760}},{{label:"2x",interval:420}},{{label:"3x",interval:280}}];
let speedIndex=0,currentIndex=0,timer=null,isPlaying=false,lastFrameAt=0,frameAccumulator=0;
const localeText=[payload.locale,payload.language,payload.title,payload.subtitle,labels.x,labels.y,labels.size,labels.time].filter(Boolean).join(" ");
const numberLocale=/[\u4e00-\u9fff]/.test(localeText)?"zh-CN":/[\u3040-\u30ff]/.test(localeText)?"ja-JP":/[\uac00-\ud7af]/.test(localeText)?"ko-KR":"en-US";
function num(v){{const n=Number(String(v??"").replace(/,/g,""));return Number.isFinite(n)?n:null}}
function trimZeros(text){{return String(text).replace(/\\.0+$/,"").replace(/(\\.\\d*?)0+$/,"$1")}}
function compactNumber(v){{const n=num(v);if(n==null)return v??"-";const abs=Math.abs(n);let scaled=n,unit="";const cjkUnits=numberLocale==="ja-JP"?[["兆",1e12],["億",1e8],["万",1e4]]:numberLocale==="ko-KR"?[["조",1e12],["억",1e8],["만",1e4]]:numberLocale==="zh-CN"?[["万亿",1e12],["亿",1e8],["万",1e4]]:null;if(cjkUnits){{const matched=cjkUnits.find(([,threshold])=>abs>=threshold);if(matched){{scaled=n/matched[1];unit=matched[0]}}}}else if(abs>=1e4){{if(abs>=1e12){{scaled=n/1e12;unit="T"}}else if(abs>=1e9){{scaled=n/1e9;unit="B"}}else if(abs>=1e6){{scaled=n/1e6;unit="M"}}else{{scaled=n/1e3;unit="K"}}}}const digits=Math.abs(scaled)>=100?0:Math.abs(scaled)>=10?1:2;return new Intl.NumberFormat(numberLocale,{{maximumFractionDigits:digits}}).format(Number(trimZeros(scaled.toFixed(digits))))+unit}}
function fmt(v){{const n=num(v);return n==null?(v??"-"):new Intl.NumberFormat(numberLocale,{{maximumFractionDigits:2}}).format(n)}}
function frameValue(row){{return enc.time?String(row[enc.time]??""):"全部"}}
function sortFrames(values){{return values.sort((a,b)=>{{const na=num(a),nb=num(b);if(na!=null&&nb!=null)return na-nb;return String(a).localeCompare(String(b),"zh-CN",{{numeric:true}});}})}}
function compact(){{return chart.getWidth()<720}}
function layout(){{
 const small=compact();
 return {{
  gridLeft:0,
  gridRight:1,
  top:small?104:128,
  bottom:small?76:84
 }};
}}
function applyLayoutToDom(){{
 const l=layout();
 const wrap=document.getElementById("wrap");
 wrap.style.setProperty("--grid-left",l.gridLeft+"px");
 wrap.style.setProperty("--grid-right",l.gridRight+"px");
}}
function renderLegend(){{
 legendEl.replaceChildren();
 legendEl.style.display=hasGrouping?"flex":"none";
 if(!hasGrouping)return;
 groups.forEach((group,index)=>{{
  const item=document.createElement("span");
  item.className="legendItem";
  const dot=document.createElement("i");
  dot.className="legendDot";
  dot.style.background=palette[index%palette.length];
  const text=document.createElement("span");
  text.textContent=group;
  item.append(dot,text);
  legendEl.appendChild(item);
 }});
}}
function validRowsForFrame(frame){{return rows.filter(r=>frameValue(r)===frame&&num(r[enc.x])!=null&&num(r[enc.y])!=null&&num(r[enc.size])!=null)}}
function extent(values){{
 const clean=values.filter(v=>v!=null);
 if(!clean.length)return [0,1];
 let min=Math.min(...clean),max=Math.max(...clean);
 if(min===max){{const d=Math.abs(min)||1;return [min-d*.1,max+d*.1]}}
 const range=max-min;
 const power=Math.pow(10,Math.floor(Math.log10(range)));
 const ratio=range/power;
 const step=ratio<2?power/5:ratio<5?power/2:power;
 const zeroBased=min>=0&&min/Math.max(max,1)<.12;
 const low=zeroBased?0:Math.floor((min-step*.35)/step)*step;
 const high=Math.ceil((max+step*.35)/step)*step;
 return [low,high>low?high:low+step];
}}
function axisScale(values){{
 const bounds=extent(values);
 const min=bounds[0],max=bounds[1];
 const span=max-min||1;
 return {{min,max,interval:span/4}};
}}
const frames=sortFrames([...new Set(rows.map(frameValue).filter(Boolean))]);
const groups=[...new Set(rows.map(r=>String(r[enc.series]??"Series")).filter(Boolean))];
const hasGrouping=enc.series&&enc.series!=="__series"&&groups.length>1;
const maxSize=Math.max(...rows.map(r=>num(r[enc.size])||0),1);
function getFrame(){{return frames[Math.max(0,Math.min(currentIndex,frames.length-1))]||""}}
function setPlayState(){{playBtn.classList.toggle("is-playing",isPlaying);playBtn.setAttribute("aria-label",isPlaying?"暂停":"播放")}}
function setTimelineState(){{const max=Math.max(frames.length-1,0);range.max=String(max);range.value=String(currentIndex);const pct=max?currentIndex/max*100:0;sliderFill.style.width=pct+"%";startLabel.textContent=frames[0]||"";endLabel.textContent=frames[frames.length-1]||"";const endWidth=Math.ceil(endLabel.getBoundingClientRect().width||0);document.getElementById("sliderWrap").style.setProperty("--end-label-space",(endWidth+(compact()?7:8))+"px");}}
function buildSeries(frame){{
 const frameRows=validRowsForFrame(frame);
 const labelLimit=compact()?6:12;
 const labelNames=new Set([...frameRows].sort((a,b)=>(num(b[enc.size])||0)-(num(a[enc.size])||0)).slice(0,labelLimit).map(r=>String(r[enc.name]??"")));
 if(!hasGrouping){{
  return [{{
   id:"bubble-all",
   name:"Series",
   type:"scatter",
   animationDuration:420,
   animationDurationUpdate:Math.min(speedPresets[speedIndex].interval*.86,520),
   animationEasing:"cubicOut",
   animationEasingUpdate:"cubicInOut",
   symbolSize:v=>Math.max(compact()?8:10,Math.sqrt((v[2]||0)/maxSize)*(compact()?50:72)),
   label:{{show:true,formatter:p=>p.value[3],position:"inside",color:"#151922",fontSize:compact()?9:10,fontWeight:700,textBorderColor:"rgba(255,255,255,.94)",textBorderWidth:2,overflow:"truncate",width:compact()?56:78}},
   labelLayout:{{hideOverlap:true,moveOverlap:"shiftY"}},
   emphasis:{{focus:"series",scale:true,label:{{show:true,formatter:p=>p.value[3],position:"top",color:"#151922",fontWeight:750,textBorderColor:"#fff",textBorderWidth:2}}}},
   data:frameRows.map((r,index)=>{{
    const name=String(r[enc.name]??"");
    const size=num(r[enc.size])||0;
    const ratio=Math.sqrt(size/maxSize);
    return {{
     name,
     value:[num(r[enc.x]),num(r[enc.y]),size,name,""],
     itemStyle:{{color:palette[index%palette.length],opacity:.76,borderColor:"rgba(255,255,255,.96)",borderWidth:1.5}},
     label:{{show:labelNames.has(name),position:ratio<.2?"top":"inside"}}
    }}
   }})
  }}];
 }}
 return groups.map((g,index)=>({{
  id:"bubble-"+index,
  name:g,
  type:"scatter",
  animationDuration:420,
  animationDurationUpdate:Math.min(speedPresets[speedIndex].interval*.86,520),
  animationEasing:"cubicOut",
  animationEasingUpdate:"cubicInOut",
  symbolSize:v=>Math.max(compact()?8:10,Math.sqrt((v[2]||0)/maxSize)*(compact()?50:72)),
  label:{{show:true,formatter:p=>p.value[3],position:"inside",color:"#151922",fontSize:compact()?9:10,fontWeight:700,textBorderColor:"rgba(255,255,255,.94)",textBorderWidth:2,overflow:"truncate",width:compact()?56:78}},
  labelLayout:{{hideOverlap:true,moveOverlap:"shiftY"}},
  itemStyle:{{color:palette[index%palette.length],opacity:.76,borderColor:"rgba(255,255,255,.96)",borderWidth:1.5}},
  emphasis:{{focus:"series",scale:true,label:{{show:true,formatter:p=>p.value[3],position:"top",color:"#151922",fontWeight:750,textBorderColor:"#fff",textBorderWidth:2}}}},
  data:frameRows.filter(r=>String(r[enc.series]??"Series")===g).map(r=>{{
   const name=String(r[enc.name]??"");
   const size=num(r[enc.size])||0;
   const ratio=Math.sqrt(size/maxSize);
   return {{
    name,
    value:[num(r[enc.x]),num(r[enc.y]),size,name,String(r[enc.series]??"Series")],
    label:{{show:labelNames.has(name),position:ratio<.2?"top":"inside"}}
   }}
  }})
 }}));
}}
function renderChart(){{
 const frame=getFrame();
 const frameRows=validRowsForFrame(frame);
 const xScale=axisScale(frameRows.map(r=>num(r[enc.x])));
 const yScale=axisScale(frameRows.map(r=>num(r[enc.y])));
 const l=layout();
 applyLayoutToDom();
 setTimelineState();
  chart.setOption({{
  color:palette,
  animation:true,
  animationDurationUpdate:Math.min(speedPresets[speedIndex].interval*.86,520),
  animationEasingUpdate:"cubicInOut",
  grid:{{left:l.gridLeft,right:l.gridRight,top:l.top,bottom:l.bottom,containLabel:true}},
  legend:{{show:false}},
  tooltip:{{className:"generic-canvas-tooltip",trigger:"item",backgroundColor:"rgba(255,255,255,.98)",borderColor:"#dfe5ee",extraCssText:"box-shadow:0 12px 28px rgba(17,24,39,.12);",textStyle:{{color:"#151922"}},formatter:p=>`<b>${{p.value[3]}}</b><br/>${{labels.time||enc.time||"time"}}: ${{frame}}<br/>${{labels.x||enc.x}}: ${{compactNumber(p.value[0])}}<br/>${{labels.y||enc.y}}: ${{compactNumber(p.value[1])}}<br/>${{labels.size||enc.size}}: ${{compactNumber(p.value[2])}}<br/>${{p.value[4]||""}}`}},
  xAxis:{{type:"value",min:xScale.min,max:xScale.max,interval:xScale.interval,splitNumber:4,name:"",axisLabel:{{color:"#687386",formatter:v=>compactNumber(v),margin:10,hideOverlap:true,showMinLabel:false,showMaxLabel:false}},axisLine:{{lineStyle:{{color:"#d9e0ea"}}}},axisTick:{{show:false}},splitLine:{{lineStyle:{{color:"rgba(104,115,134,.12)"}}}}}},
  yAxis:{{type:"value",min:yScale.min,max:yScale.max,interval:yScale.interval,splitNumber:4,name:"",axisLabel:{{color:"#687386",formatter:v=>compactNumber(v),inside:false,align:"right",padding:0,margin:3,hideOverlap:true}},axisLine:{{show:true,lineStyle:{{color:"#d9e0ea"}}}},axisTick:{{show:false}},splitLine:{{lineStyle:{{color:"rgba(104,115,134,.12)"}}}}}},
  graphic:[
   {{type:"text",left:"center",top:"45%",silent:true,z:1,style:{{text:frame,fill:"rgba(104,115,134,.13)",fontSize:compact()?42:64,fontWeight:800,textAlign:"center",textVerticalAlign:"middle"}}}},
   {{type:"text",x:0,y:l.top-24,silent:true,z:4,style:{{text:labels.y||enc.y,fill:"#687386",fontSize:compact()?12:13,fontWeight:650,textAlign:"left",textVerticalAlign:"middle"}}}},
   {{type:"text",x:chart.getWidth()-8,y:chart.getHeight()-l.bottom+(compact()?16:18),silent:true,z:4,style:{{text:labels.x||enc.x,fill:"#687386",fontSize:compact()?12:13,fontWeight:650,textAlign:"right",textVerticalAlign:"middle"}}}}
  ],
  series:buildSeries(frame)
 }},{{notMerge:false,lazyUpdate:true}});
 postChartHeight();
}}
function stopTimer(){{if(timer){{cancelAnimationFrame(timer);timer=null}}lastFrameAt=0;frameAccumulator=0}}
function startTimer(){{stopTimer();const tick=(timestamp)=>{{if(!isPlaying)return;if(!lastFrameAt)lastFrameAt=timestamp;const interval=speedPresets[speedIndex].interval;const delta=Math.min(timestamp-lastFrameAt,interval*1.5);lastFrameAt=timestamp;frameAccumulator+=delta;if(frameAccumulator>=interval){{const steps=Math.max(1,Math.floor(frameAccumulator/interval));frameAccumulator%=interval;currentIndex=Math.min(currentIndex+steps,frames.length-1);renderChart();if(currentIndex>=frames.length-1){{isPlaying=false;setPlayState();renderChart();stopTimer();return}}}}timer=requestAnimationFrame(tick);}};timer=requestAnimationFrame(tick)}}
function postChartHeight(){{const wrap=document.getElementById("wrap");const height=Math.ceil(Math.max(180,(wrap&&wrap.getBoundingClientRect().height)||document.documentElement.clientHeight||document.body.scrollHeight||0)+2);try{{parent.postMessage({{type:"analysis-planner-chart-height",height}},"*")}}catch(e){{}}}}
if(!rows.length||!enc.x||!enc.y||!enc.size){{empty.style.display="flex";timelineBar.classList.add("is-hidden");postChartHeight();}}else{{
 timelineBar.classList.toggle("is-hidden",frames.length<=1);
 speedBtn.textContent=speedPresets[speedIndex].label;
 playBtn.addEventListener("click",()=>{{if(frames.length<=1)return;if(currentIndex>=frames.length-1)currentIndex=0;isPlaying=!isPlaying;setPlayState();if(isPlaying)startTimer();else stopTimer();renderChart();}});
 speedBtn.addEventListener("click",()=>{{speedIndex=(speedIndex+1)%speedPresets.length;speedBtn.textContent=speedPresets[speedIndex].label;if(isPlaying)startTimer();}});
 range.addEventListener("input",()=>{{currentIndex=Number(range.value)||0;isPlaying=false;setPlayState();stopTimer();renderChart();}});
 addEventListener("resize",()=>{{chart.resize();renderChart();postChartHeight();}});
 renderLegend();setPlayState();renderChart();setTimeout(postChartHeight,80);setTimeout(postChartHeight,300);
}}
</script>{(Path(__file__).resolve().parents[1] / "runtime/mobile_interactions.html").read_text(encoding="utf-8")}
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code")
    parser.add_argument("--title")
    parser.add_argument("--payload")
    parser.add_argument("--data-json")
    parser.add_argument("--data")
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    args, _ = parser.parse_known_args()
    payload = load_payload(args)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(payload), encoding="utf-8")
    if args.payload_output:
        Path(args.payload_output).expanduser().resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "chartName": "dynamic_bubble"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
