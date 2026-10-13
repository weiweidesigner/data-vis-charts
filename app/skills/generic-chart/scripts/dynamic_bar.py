#!/usr/bin/env python3
"""Standalone animated horizontal bar-race chart renderer."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


FIELD_LABELS = {
    "year": "年份",
    "time": "时间",
    "date": "日期",
    "name": "名称",
    "country": "国家",
    "category": "类别",
    "value": "数值",
    "amount": "金额",
    "count": "数量",
    "score": "得分",
    "population": "人口",
    "gdp": "GDP",
    "gdp_per_capita": "人均GDP",
    "revenue": "营收",
    "market_cap": "市值",
    "marketcap": "市值",
    "continent": "洲别",
    "region": "地区",
}


def parse_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def rows_of(data: Any) -> list[dict[str, Any]]:
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def is_number(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        float(str(value).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


def humanize_field(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    key = text.lower()
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    return re.sub(r"[_\-]+", " ", text).strip()


def normalize_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("chartPayload"), dict):
        payload = dict(raw["chartPayload"])
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        payload = {"data": raw}

    if not isinstance(payload.get("encode"), dict):
        encode: dict[str, Any] = {}
        aliases = {
            "time": ("timeField", "frameField"),
            "name": ("nameField", "categoryField", "labelField"),
            "value": ("valueField", "xField", "yField"),
            "color": ("colorField", "groupField", "seriesField"),
        }
        for channel, keys in aliases.items():
            for key in keys:
                if payload.get(key):
                    encode[channel] = payload[key]
                    break
        if encode:
            payload["encode"] = encode
    return payload


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


def infer_encode(payload: dict[str, Any]) -> dict[str, str]:
    rows = rows_of(payload.get("data"))
    encode = payload.get("encode") if isinstance(payload.get("encode"), dict) else {}
    keys = list(rows[0].keys()) if rows else []
    lower = {key.lower(): key for key in keys}

    time = (
        encode.get("time")
        or lower.get("time")
        or lower.get("date")
        or lower.get("year")
        or lower.get("frame")
    )
    name = (
        encode.get("name")
        or encode.get("category")
        or lower.get("name")
        or lower.get("country")
        or lower.get("category")
        or lower.get("label")
    )
    value = (
        encode.get("value")
        or encode.get("x")
        or encode.get("y")
        or lower.get("value")
        or lower.get("amount")
        or lower.get("count")
        or lower.get("score")
        or lower.get("population")
        or lower.get("gdp")
    )
    color = (
        encode.get("color")
        or encode.get("series")
        or lower.get("color")
        or lower.get("group")
        or lower.get("series")
        or lower.get("continent")
        or lower.get("region")
    )

    if not time and keys:
        time = next((key for key in keys if key.lower() in {"time", "date", "year", "frame"}), keys[0])
    if not name and keys:
        name = next((key for key in keys if key != time and not is_number(rows[0].get(key))), keys[0])
    if not value and keys:
        value = next((key for key in keys if key not in {time, name} and is_number(rows[0].get(key))), keys[-1])
    if not color:
        color = "__series"
        for row in rows:
            row.setdefault(color, payload.get("title") or "Series")

    return {
        "time": str(time or "time"),
        "name": str(name or "name"),
        "value": str(value or "value"),
        "color": str(color),
    }


def infer_title(rows: list[dict[str, Any]], encode: dict[str, str], value_label: str) -> str:
    time_field = encode.get("time")
    values = [row.get(time_field) for row in rows if time_field and row.get(time_field) not in (None, "")]
    period = ""
    if values:
        def sort_key(value: Any) -> tuple[int, Any]:
            try:
                return (0, float(value))
            except (TypeError, ValueError):
                return (1, str(value))

        ordered = sorted({str(value) for value in values}, key=sort_key)
        if ordered:
            period = ordered[0] if len(ordered) == 1 else f"{ordered[0]}–{ordered[-1]}"

    base = "动态排名"
    return f"{base}（{period}）" if period else base


def clean_title(title: str, value_label: str) -> str:
    """Remove redundant metric wording immediately before “动态排名”."""
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    label = str(value_label or "").strip()
    if label:
        text = re.sub(rf"{re.escape(label)}\s*(?=动态排名)", "", text)
    text = re.sub(r"全球\s*动态排名", "全球动态排名", text)
    return text


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>__TITLE__</title>
<script src="/static/vendor/echarts.min.js"></script>
<script>window.echarts||document.write('<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"><\/script>')</script>
<style>
*{box-sizing:border-box}
html,body{margin:0;width:100%;height:auto;min-height:0;background:transparent;color:#151922;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
#wrap{position:relative;width:100%;height:320px;min-height:0;max-height:none;background:transparent;overflow:hidden}
#header{position:absolute;left:0;right:1px;top:12px;z-index:6;pointer-events:none}
#title{margin:0;padding:0;font-family:"PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;font-size:22px;line-height:1.35;font-weight:700;letter-spacing:-.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#151922}
#legend{display:flex;align-items:center;flex-wrap:wrap;gap:8px 20px;margin-top:10px;min-height:18px}
.legendItem{display:inline-flex;align-items:center;gap:7px;color:#687386;font-size:12px;line-height:18px;white-space:nowrap}
.legendDot{width:9px;height:9px;flex:0 0 9px;border-radius:50%}
#chart{position:absolute;inset:0;height:100%;min-height:100%}
#empty{display:none;position:absolute;inset:0;align-items:center;justify-content:center;color:#687386;font-size:14px;z-index:7}
#timelineBar{position:absolute;left:0;right:0;bottom:14px;z-index:8;display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:999px;background:transparent;border:1px solid transparent;backdrop-filter:none;-webkit-backdrop-filter:none;box-shadow:none}
#timelineBar.is-hidden{display:none}
#playBtn{width:28px;height:28px;position:relative;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;padding:0;border:0;border-radius:999px;background:#4c91ff;color:#fff;cursor:pointer}
#playBtn::before{content:"";width:0;height:0;border-top:4px solid transparent;border-bottom:4px solid transparent;border-left:6px solid #fff;transform:translateX(1px)}
#playBtn.is-playing::before{width:8px;height:10px;border:0;border-radius:1px;background:linear-gradient(90deg,#fff 0 36%,transparent 36% 64%,#fff 64% 100%);transform:none}
.timeLabel{min-width:58px;color:#687386;font-size:12px;line-height:1;text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}
#sliderWrap{position:relative;display:flex;align-items:center;flex:1;min-width:80px;height:28px;padding:0}
#sliderTrack{position:absolute;left:0;right:0;top:50%;height:4px;border-radius:999px;background:rgba(76,145,255,.16);transform:translateY(-50%);pointer-events:none;overflow:hidden}
#sliderFill{display:block;width:0;height:100%;border-radius:inherit;background:#4c91ff}
#timelineRange{position:absolute;inset:0;width:100%;height:28px;margin:0;appearance:none;background:transparent;cursor:pointer;z-index:2}
#timelineRange::-webkit-slider-thumb{appearance:none;width:14px;height:14px;margin-top:-5px;border-radius:999px;background:#4c91ff;border:0;box-shadow:0 0 0 5px rgba(76,145,255,.14)}
#timelineRange::-webkit-slider-runnable-track{height:4px;background:transparent}
#timelineRange::-moz-range-thumb{width:14px;height:14px;border-radius:999px;background:#4c91ff;border:0;box-shadow:0 0 0 5px rgba(76,145,255,.14)}
#timelineRange::-moz-range-track{height:4px;background:transparent}
#speedBtn{height:28px;min-height:28px;line-height:28px;min-width:42px;padding:0 10px;border-radius:999px;border:1px solid transparent;background:rgba(148,163,184,.10);color:#151922;font-size:12px;font-weight:750;cursor:pointer}
@media(max-width:720px){
 #header{top:8px}
 #title{font-size:17px}
 #legend{gap:7px 12px;margin-top:8px}
 .legendItem{font-size:11px}
 #timelineBar{bottom:12px;gap:7px;padding:5px 8px}
 .timeLabel{min-width:42px;font-size:11px}
 #speedBtn{height:28px;min-height:28px;line-height:28px;min-width:38px;padding:0 9px}
}
</style>
</head>
<body>
<div id="wrap" data-renderer-version="dynamic-bar-spacing-v5">
  <div id="header"><h1 id="title">__TITLE__</h1><div id="legend"></div></div>
  <div id="chart"></div>
  <div id="empty">暂无可渲染数据</div>
  <div id="timelineBar" class="is-hidden">
    <button id="playBtn" type="button" aria-label="播放"></button>
    <button id="speedBtn" type="button">1x</button>
    <div id="startLabel" class="timeLabel"></div>
    <div id="sliderWrap">
      <div id="sliderTrack"><span id="sliderFill"></span></div>
      <input id="timelineRange" type="range" min="0" max="0" value="0" aria-label="时间轴" />
    </div>
    <div id="endLabel" class="timeLabel"></div>
  </div>
</div>
<script>
const payload=__DATA__;
const rows=payload.rows||[];
const enc=payload.encode||{};
const unit=payload.unit||"";
const topN=Math.max(3,Number(payload.topN)||10);
const valueLabel=payload.valueLabel||enc.value||"数值";
const timeLabelText=payload.timeLabel||enc.time||"时间";
const palette=["#38bdf8","#34d399","#f97316","#a78bfa","#f43f5e","#facc15","#2dd4bf","#fb7185","#60a5fa","#f59e0b"];
const localeText=[
  payload.locale,
  payload.language,
  payload.title,
  payload.subtitle,
  payload.valueLabel,
  payload.timeLabel,
  payload.nameLabel,
  payload.groupLabel,
  unit
].filter(Boolean).join(" ");
const numberLocale=/[\u4e00-\u9fff]/.test(localeText)?"zh-CN":/[\u3040-\u30ff]/.test(localeText)?"ja-JP":/[\uac00-\ud7af]/.test(localeText)?"ko-KR":"en-US";

const empty=document.getElementById("empty");
const legendEl=document.getElementById("legend");
const timelineBar=document.getElementById("timelineBar");
const playBtn=document.getElementById("playBtn");
const speedBtn=document.getElementById("speedBtn");
const range=document.getElementById("timelineRange");
const sliderFill=document.getElementById("sliderFill");
const startLabel=document.getElementById("startLabel");
const endLabel=document.getElementById("endLabel");
const wrap=document.getElementById("wrap");
const header=document.getElementById("header");
const chart=echarts.init(document.getElementById("chart"));

const speedPresets=[{label:"1x",interval:900},{label:"2x",interval:520},{label:"3x",interval:320}];
let speedIndex=0,currentIndex=0,timer=null,isPlaying=false,lastFrameAt=0,frameAccumulator=0;

function num(v){const n=Number(String(v??"").replace(/,/g,""));return Number.isFinite(n)?n:null}
function trimZeros(text){return String(text).replace(/\.0+$/,'').replace(/(\.\d*?)0+$/,'$1')}
function compactNumber(v,includeUnit=false){
  const n=num(v);if(n==null)return v??"-";
  const abs=Math.abs(n);let scaled=n,suffix="";
  const cjkUnits=numberLocale==="ja-JP"?[["兆",1e12],["億",1e8],["万",1e4]]:numberLocale==="ko-KR"?[["조",1e12],["억",1e8],["만",1e4]]:numberLocale==="zh-CN"?[["万亿",1e12],["亿",1e8],["万",1e4]]:null;
  if(cjkUnits){
    const matched=cjkUnits.find(([,threshold])=>abs>=threshold);
    if(matched){scaled=n/matched[1];suffix=matched[0]}
  }else if(abs>=1e4){
    if(abs>=1e12){scaled=n/1e12;suffix="T"}
    else if(abs>=1e9){scaled=n/1e9;suffix="B"}
    else if(abs>=1e6){scaled=n/1e6;suffix="M"}
    else {scaled=n/1e3;suffix="K"}
  }
  const digits=Math.abs(scaled)>=100?0:Math.abs(scaled)>=10?1:2;
  return new Intl.NumberFormat(numberLocale,{maximumFractionDigits:digits}).format(Number(trimZeros(scaled.toFixed(digits))))+suffix+(includeUnit?unit:"");
}
function frameValue(row){return String(row[enc.time]??"")}
function itemName(row){return String(row[enc.name]??"")}
function groupName(row){return String(row[enc.color]??"Series")}
function sortFrames(values){
  return values.sort((a,b)=>{
    const na=num(a),nb=num(b);
    if(na!=null&&nb!=null)return na-nb;
    return String(a).localeCompare(String(b),"zh-CN",{numeric:true});
  });
}
function compact(){return chart.getWidth()<720}
const measureCanvas=document.createElement("canvas");
const measureContext=measureCanvas.getContext("2d");
function labelFont(){return `${compact()?11:12}px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif`}
function textWidth(text){
  if(!measureContext)return String(text).length*(compact()?11:12);
  measureContext.font=labelFont();
  return measureContext.measureText(String(text)).width;
}
function truncateText(text,maxWidth){
  const source=String(text);
  if(textWidth(source)<=maxWidth)return source;
  const ellipsis="…";
  let low=0,high=source.length;
  while(low<high){
    const mid=Math.ceil((low+high)/2);
    if(textWidth(source.slice(0,mid)+ellipsis)<=maxWidth)low=mid;else high=mid-1;
  }
  return source.slice(0,Math.max(0,low))+ellipsis;
}
function layout(axisLabels){
  const small=compact();
  const labelLimit=small?72:104;
  const labelWidth=Math.min(labelLimit,Math.max(0,...axisLabels.map(textWidth)));
  const headerHeight=Math.ceil(header.getBoundingClientRect().height||0);
  const headerTop=small?8:12;
  const timelineVisible=!timelineBar.classList.contains("is-hidden");
  const timelineHeight=timelineVisible?Math.ceil(timelineBar.getBoundingClientRect().height||46):0;
  const timelineBottom=timelineVisible?(small?12:14):0;
  const playerGap=timelineVisible?(small?10:14):0;
  const xAxisLabelSpace=small?18:22;
  return {
    left:Math.ceil(labelWidth)+3,
    right:1,
    top:headerTop+headerHeight+(small?14:16),
    bottom:timelineBottom+timelineHeight+playerGap+xAxisLabelSpace,
    labelLimit
  };
}
function contentHeight(frameRows){
  const small=compact();
  const headerHeight=Math.ceil(header.getBoundingClientRect().height||0);
  const headerTop=small?8:12;
  const timelineVisible=!timelineBar.classList.contains("is-hidden");
  const timelineHeight=timelineVisible?Math.ceil(timelineBar.getBoundingClientRect().height||46):0;
  const timelineBottom=timelineVisible?(small?12:14):0;
  const playerGap=timelineVisible?(small?10:14):0;
  const xAxisLabelSpace=small?18:22;
  const top=headerTop+headerHeight+(small?14:16);
  const bottom=timelineBottom+timelineHeight+playerGap+xAxisLabelSpace;
  const rowSlot=small?32:40;
  const minPlot=small?132:160;
  const rowCount=Math.max(1,frameRows.length);
  return Math.ceil(top+bottom+Math.max(minPlot,rowCount*rowSlot));
}
function resizeToContent(frameRows){
  const height=contentHeight(frameRows);
  if(Math.abs(wrap.getBoundingClientRect().height-height)>1){
    wrap.style.height=`${height}px`;
    chart.resize();
  }
}
function postChartHeight(){
  const height=Math.ceil(Math.max(180,(wrap&&wrap.getBoundingClientRect().height)||document.body.scrollHeight||0))+2;
  try{parent.postMessage({type:"analysis-planner-chart-height",height},"*")}catch(e){}
}

const frames=sortFrames([...new Set(rows.map(frameValue).filter(Boolean))]);
const hasGrouping=Boolean(enc.color&&enc.color!=="__series");
const groups=hasGrouping?[...new Set(rows.map(groupName).filter(Boolean))]:[];
const groupColorMap=new Map(groups.map((g,i)=>[g,palette[i%palette.length]]));
const itemColorMap=new Map();

// 有分类层级时，同组对象使用同一颜色；无分类层级时，每个对象按首次出现顺序依次使用色板颜色。
rows.forEach(row=>{
  const name=itemName(row);
  if(!name||itemColorMap.has(name))return;
  if(hasGrouping){
    itemColorMap.set(name,groupColorMap.get(groupName(row))||palette[0]);
  }else{
    itemColorMap.set(name,palette[itemColorMap.size%palette.length]);
  }
});

function renderLegend(){
  legendEl.innerHTML="";
  legendEl.style.display=hasGrouping?"flex":"none";
  if(!hasGrouping)return;
  groups.forEach(group=>{
    const item=document.createElement("span");item.className="legendItem";
    const dot=document.createElement("span");dot.className="legendDot";dot.style.background=groupColorMap.get(group)||palette[0];
    const text=document.createElement("span");text.textContent=group;
    item.append(dot,text);legendEl.appendChild(item);
  });
}
renderLegend();

function rowsForFrame(frame){
  return rows
    .filter(row=>frameValue(row)===frame&&num(row[enc.value])!=null)
    .map(row=>({
      name:itemName(row),
      group:groupName(row),
      value:num(row[enc.value])||0,
      color:itemColorMap.get(itemName(row))||(hasGrouping?groupColorMap.get(groupName(row)):null)||palette[0]
    }))
    .sort((a,b)=>b.value-a.value)
    .slice(0,topN);
}
function niceMax(value){
  if(!(value>0))return 1;
  const exp=Math.floor(Math.log10(value));
  const frac=value/Math.pow(10,exp);
  const niceFrac=frac<=1?1:frac<=2?2:frac<=5?5:10;
  return niceFrac*Math.pow(10,exp);
}
function niceInterval(value){
  if(!(value>0))return 1;
  const exp=Math.floor(Math.log10(value));
  const frac=value/Math.pow(10,exp);
  const niceFrac=frac<=1?1:frac<=2?2:frac<=2.5?2.5:frac<=5?5:10;
  return niceFrac*Math.pow(10,exp);
}
function axisScale(frameRows,l){
  const maxValue=Math.max(...frameRows.map(d=>d.value),0);
  if(!(maxValue>0))return {min:0,max:1,interval:.25};

  const small=compact();
  const labelDistance=6;
  const safetyGap=1;
  const maxLabelText=compactNumber(maxValue,false);
  const valueFontSize=small?11:12;
  const previousFont=measureContext?measureContext.font:"";
  if(measureContext)measureContext.font=`600 ${valueFontSize}px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif`;
  const labelWidth=Math.ceil(measureContext?measureContext.measureText(maxLabelText).width:maxLabelText.length*valueFontSize);
  if(measureContext)measureContext.font=previousFont;

  const plotWidth=Math.max(1,chart.getWidth()-l.left-l.right);
  const reservedPixels=labelDistance+labelWidth+safetyGap;
  const maxFillByLabel=Math.max(.62,1-(reservedPixels/plotWidth)-.03);
  const targetFill=Math.min(.74,maxFillByLabel);
  const scaled=maxValue/targetFill;
  return {min:0,max:scaled,interval:niceInterval(scaled/4)};
}
function getFrame(){return frames[Math.max(0,Math.min(currentIndex,frames.length-1))]||""}
function setPlayState(){
  playBtn.classList.toggle("is-playing",isPlaying);
  playBtn.setAttribute("aria-label",isPlaying?"暂停":"播放");
}
function setTimelineState(){
  const max=Math.max(frames.length-1,0);
  range.max=String(max);range.value=String(currentIndex);
  sliderFill.style.width=(max?currentIndex/max*100:0)+"%";
  startLabel.textContent=frames[0]||"";
  endLabel.textContent=frames[frames.length-1]||"";
}

function renderChart(){
  const frame=getFrame();
  const frameRows=rowsForFrame(frame);
  setTimelineState();
  resizeToContent(frameRows);
  const small=compact();
  const labelLimit=small?72:104;
  const labelMap=new Map(frameRows.map(d=>[d.name,truncateText(d.name,labelLimit)]));
  const l=layout([...labelMap.values()]);
  const scale=axisScale(frameRows,l);

  chart.setOption({
    animation:true,
    animationDuration:420,
    animationDurationUpdate:Math.min(speedPresets[speedIndex].interval*.84,520),
    animationEasing:"cubicOut",
    animationEasingUpdate:"cubicInOut",
    grid:{left:l.left,right:l.right,top:l.top,bottom:l.bottom,containLabel:false},
    tooltip:{
      trigger:"item",
      backgroundColor:"rgba(255,255,255,.98)",
      borderColor:"#dfe5ee",
      textStyle:{color:"#151922"},
      formatter:p=>`<b>${p.name}</b><br/>${timeLabelText}: ${frame}<br/>${valueLabel}: ${compactNumber(p.value,true)}`
    },
    xAxis:{
      type:"value",min:scale.min,max:scale.max,interval:scale.interval,splitNumber:4,
      axisLabel:{color:"#687386",formatter:v=>compactNumber(v,false),hideOverlap:true,showMinLabel:false,showMaxLabel:false,margin:8},
      axisLine:{show:false},axisTick:{show:false},
      splitLine:{show:true,lineStyle:{color:"rgba(104,115,134,.13)"}}
    },
    yAxis:{
      type:"category",inverse:true,
      data:frameRows.map(d=>d.name),
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{
        color:"#4b5563",
        fontSize:small?11:12,
        margin:3,
        padding:0,
        align:"right",
        formatter:value=>labelMap.get(value)||value
      },
      animationDurationUpdate:Math.min(speedPresets[speedIndex].interval*.84,520)
    },
    graphic:[
      {type:"text",left:"center",top:"42%",silent:true,z:1,style:{text:frame,fill:"rgba(104,115,134,.12)",fontSize:compact()?46:62,fontWeight:800,textAlign:"center",textVerticalAlign:"middle"}}
    ],
    series:[{
      type:"bar",
      realtimeSort:true,
      data:frameRows.map(d=>({id:d.name,name:d.name,value:d.value,itemStyle:{color:d.color,borderRadius:[0,7,7,0]}})),
      universalTransition:true,
      barWidth:small?16:22,
      barCategoryGap:"34%",
      showBackground:true,
      backgroundStyle:{color:"rgba(104,115,134,.07)",borderRadius:[0,7,7,0]},
      label:{show:true,position:"right",distance:6,color:"#374151",fontSize:small?11:12,fontWeight:600,formatter:p=>compactNumber(p.value,false)},
      emphasis:{focus:"series"}
    }]
  },{notMerge:false,lazyUpdate:true});
  postChartHeight();
}

function stopTimer(){
  if(timer){cancelAnimationFrame(timer);timer=null}
  lastFrameAt=0;frameAccumulator=0;
}
function startTimer(){
  stopTimer();
  const tick=timestamp=>{
    if(!isPlaying)return;
    if(!lastFrameAt)lastFrameAt=timestamp;
    const interval=speedPresets[speedIndex].interval;
    const delta=Math.min(timestamp-lastFrameAt,interval*1.5);
    lastFrameAt=timestamp;frameAccumulator+=delta;
    if(frameAccumulator>=interval){
      const steps=Math.max(1,Math.floor(frameAccumulator/interval));
      frameAccumulator%=interval;
      currentIndex=Math.min(currentIndex+steps,frames.length-1);
      renderChart();
      if(currentIndex>=frames.length-1){
        isPlaying=false;setPlayState();renderChart();stopTimer();return;
      }
    }
    timer=requestAnimationFrame(tick);
  };
  timer=requestAnimationFrame(tick);
}

if(!rows.length||!enc.time||!enc.name||!enc.value){
  empty.style.display="flex";
  timelineBar.classList.add("is-hidden");
  postChartHeight();
}else{
  timelineBar.classList.toggle("is-hidden",frames.length<=1);
  speedBtn.textContent=speedPresets[speedIndex].label;
  playBtn.addEventListener("click",()=>{
    if(frames.length<=1)return;
    if(currentIndex>=frames.length-1)currentIndex=0;
    isPlaying=!isPlaying;setPlayState();
    if(isPlaying)startTimer();else stopTimer();
    renderChart();
  });
  speedBtn.addEventListener("click",()=>{
    speedIndex=(speedIndex+1)%speedPresets.length;
    speedBtn.textContent=speedPresets[speedIndex].label;
    if(isPlaying)startTimer();
  });
  range.addEventListener("input",()=>{
    currentIndex=Number(range.value)||0;
    isPlaying=false;setPlayState();stopTimer();renderChart();
  });
  addEventListener("resize",()=>{chart.resize();renderChart();postChartHeight()});
  setPlayState();renderChart();setTimeout(postChartHeight,80);setTimeout(postChartHeight,300);
}
</script>
</body>
</html>'''


def build_html(payload: dict[str, Any]) -> str:
    rows = rows_of(payload.get("data"))
    encode = infer_encode(payload)
    value_label = str(
        payload.get("valueLabel")
        or payload.get("xLabel")
        or payload.get("yLabel")
        or humanize_field(encode.get("value"))
        or "数值"
    )
    time_label = str(payload.get("timeLabel") or humanize_field(encode.get("time")) or "时间")
    raw_title = str(payload.get("title") or infer_title(rows, encode, value_label))
    title = clean_title(raw_title, value_label)

    packed = json.dumps(
        {
            "rows": rows,
            "encode": encode,
            "unit": str(payload.get("unit") or ""),
            "topN": int(payload.get("topN") or 10),
            "valueLabel": value_label,
            "timeLabel": time_label,
        },
        ensure_ascii=False,
    )
    return HTML_TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", packed)


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
        Path(args.payload_output).expanduser().resolve().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps({"ok": True, "output": str(output), "chartName": "dynamic_bar"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
