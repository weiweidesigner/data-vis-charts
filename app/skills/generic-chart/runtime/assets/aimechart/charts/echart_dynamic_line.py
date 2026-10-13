from typing import Dict, Any, List, Optional

from utils.common import ensure_str, json_dumps
from utils.bgm import pick_background_music_base64
from utils.normalize import normalize_dynamic_line_dataset


def build_dynamic_line_html(payload: Dict[str, Any], debug_logs: Optional[List[str]] = None) -> str:
    if debug_logs is None:
        debug_logs = []

    title = ensure_str(payload.get("title"), "动态折线图")
    unit = ensure_str(payload.get("unit"), "")
    dataset = normalize_dynamic_line_dataset(payload)

    bgm_info = pick_background_music_base64(payload, debug_logs)
    bgm_data_uri = bgm_info["data_uri"]
    bgm_filename = bgm_info["filename"]

    debug_logs.append("dynamic_line 初始化开始")
    debug_logs.append(f"title = {title}")
    debug_logs.append(f"unit = {unit}")
    debug_logs.append(f"xKey = {dataset.get('xKey')}")
    debug_logs.append(f"yKey = {dataset.get('yKey')}")
    debug_logs.append(f"seriesKey = {dataset.get('seriesKey')}")
    debug_logs.append(f"rows.length = {len(dataset.get('rows', []))}")
    debug_logs.append(f"seriesList.length = {len(dataset.get('seriesList', []))}")
    debug_logs.append(f"xList.length = {len(dataset.get('xList', []))}")
    debug_logs.append(f"bgm.filename = {bgm_filename or '未找到'}")

    title_json = json_dumps(title)
    unit_json = json_dumps(unit)
    x_key_json = json_dumps(dataset["xKey"])
    y_key_json = json_dumps(dataset["yKey"])
    series_key_json = json_dumps(dataset["seriesKey"])
    rows_json = json_dumps(dataset["rows"])
    series_list_json = json_dumps(dataset["seriesList"])
    x_list_json = json_dumps(dataset["xList"])
    bgm_data_uri_json = json_dumps(bgm_data_uri)
    bgm_filename_json = json_dumps(bgm_filename)

    html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      background: #0b0e14;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      overflow: hidden;
    }}

    #wrap {{
      position: relative;
      width: 100%;
      height: 100vh;
      background:
        radial-gradient(circle at top, rgba(30, 64, 175, 0.16), transparent 36%),
        #0b0e14;
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(51, 65, 85, 0.42);
      box-sizing: border-box;
    }}

    #chart {{
      width: 100%;
      height: 100vh;
    }}

    #timelineBar {{
      position: absolute;
      left: 14px;
      right: 14px;
      bottom: 12px;
      z-index: 30;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 16px;
      background: rgba(15, 23, 42, 0.84);
      border: 1px solid rgba(59, 80, 120, 0.42);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
      box-sizing: border-box;
    }}

    #playBtn {{
      flex: 0 0 auto;
      width: 30px;
      height: 30px;
      border-radius: 999px;
      border: 1px solid rgba(96, 165, 250, 0.24);
      background: linear-gradient(180deg, #377dff 0%, #1d4ed8 100%);
      color: #ffffff;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      line-height: 1;
      box-shadow: 0 6px 16px rgba(37, 99, 235, 0.24);
    }}

    #playBtn:active {{
      transform: scale(0.96);
    }}

    .pillBtn {{
      flex: 0 0 auto;
      height: 30px;
      min-width: 42px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: rgba(17, 24, 39, 0.92);
      color: #dbe7ff;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.2px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }}

    .pillBtn:active {{
      transform: scale(0.98);
    }}

    #musicBtn {{
      width: 30px;
      min-width: 30px;
      padding: 0;
      color: #9fb3d9;
    }}

    #musicBtn.on {{
      background: rgba(30, 64, 175, 0.88);
      border-color: rgba(96, 165, 250, 0.58);
      color: #ffffff;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
    }}

    #musicBtn.off {{
      background: rgba(17, 24, 39, 0.92);
      color: #94a3b8;
    }}

    #musicBtn.disabled {{
      opacity: 0.42;
      cursor: not-allowed;
      box-shadow: none;
    }}

    #musicBtn svg {{
      width: 14px;
      height: 14px;
      display: block;
    }}

    .timeLabel {{
      flex: 0 0 auto;
      color: #91a4c6;
      font-size: 10px;
      font-weight: 500;
      line-height: 1.05;
      white-space: nowrap;
      min-width: 38px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
    }}

    .timeLabel .md {{
      font-size: 10px;
      color: #dbe5f3;
      font-weight: 600;
      line-height: 1.05;
      width: 100%;
    }}

    .timeLabel .yy {{
      font-size: 9px;
      color: #8192ad;
      font-weight: 500;
      line-height: 1.05;
      margin-top: 1px;
      width: 100%;
    }}

    #sliderWrap {{
      position: relative;
      flex: 1 1 auto;
      height: 22px;
      display: flex;
      align-items: center;
      min-width: 0;
    }}

    #sliderTrack {{
      position: absolute;
      left: 0;
      right: 0;
      top: 50%;
      transform: translateY(-50%);
      height: 4px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.18);
      pointer-events: none;
    }}

    #sliderProgress {{
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      height: 4px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(56, 189, 248, 0.92), rgba(59, 130, 246, 0.96));
      pointer-events: none;
      width: 0%;
      box-shadow: 0 0 14px rgba(56, 189, 248, 0.22);
    }}

    #timelineRange {{
      position: relative;
      width: 100%;
      margin: 0;
      appearance: none;
      -webkit-appearance: none;
      background: transparent;
      height: 22px;
      cursor: pointer;
      z-index: 2;
    }}

    #timelineRange::-webkit-slider-runnable-track {{
      height: 4px;
      background: transparent;
      border-radius: 999px;
    }}

    #timelineRange::-moz-range-track {{
      height: 4px;
      background: transparent;
      border-radius: 999px;
    }}

    #timelineRange::-webkit-slider-thumb {{
      -webkit-appearance: none;
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: #ffffff;
      border: 2px solid #4ea1ff;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.14);
      margin-top: -4px;
    }}

    #timelineRange::-moz-range-thumb {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: #ffffff;
      border: 2px solid #4ea1ff;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.14);
    }}

    #errorBox {{
      display: none;
      box-sizing: border-box;
      padding: 16px 18px;
      color: #fca5a5;
      background: #0b0e14;
      font-family: Arial, sans-serif;
      white-space: pre-wrap;
      line-height: 1.7;
      font-size: 14px;
    }}

    @media (max-width: 768px) {{
      #wrap {{
        border-radius: 16px;
      }}

      #timelineBar {{
        left: 10px;
        right: 10px;
        bottom: 10px;
        gap: 6px;
        padding: 7px 8px;
        border-radius: 15px;
      }}

      #playBtn,
      .pillBtn,
      #musicBtn {{
        height: 28px;
      }}

      #playBtn,
      #musicBtn {{
        width: 28px;
        min-width: 28px;
      }}

      .pillBtn {{
        min-width: 40px;
        padding: 0 9px;
        font-size: 10px;
      }}

      .timeLabel {{
        min-width: 34px;
      }}

      .timeLabel .md {{
        font-size: 9px;
      }}

      .timeLabel .yy {{
        font-size: 8px;
      }}
    }}
  </style>
</head>
<body>
  <div id="wrap">
    <div id="chart"></div>

    <div id="timelineBar">
      <button id="playBtn" type="button" aria-label="播放">▶</button>
      <button id="speedBtn" class="pillBtn" type="button" aria-label="播放速度">1x</button>
      <div id="startLabel" class="timeLabel"></div>
      <div id="sliderWrap">
        <div id="sliderTrack"></div>
        <div id="sliderProgress"></div>
        <input id="timelineRange" type="range" min="0" max="0" value="0" step="1" />
      </div>
      <div id="endLabel" class="timeLabel"></div>
      <button id="musicBtn" class="pillBtn off" type="button" aria-label="背景音乐开关" title="背景音乐已关闭">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M14.5 4.5a1 1 0 0 1 1.7.7v13.6a1 1 0 0 1-1.7.7l-4.7-4.5H6a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2h3.8l4.7-4.5Z"></path>
          <path d="M18.2 9.1a1 1 0 0 1 1.4 0 5 5 0 0 1 0 7.1 1 1 0 0 1-1.4-1.4 3 3 0 0 0 0-4.3 1 1 0 0 1 0-1.4Z"></path>
        </svg>
      </button>
    </div>

    <div id="errorBox"></div>
    <audio id="bgmAudio" preload="auto" loop playsinline webkit-playsinline></audio>
  </div>

  <script>
    const chart = echarts.init(document.getElementById('chart'));
    const chartDom = document.getElementById('chart');
    const errorBox = document.getElementById('errorBox');

    const title = {title_json};
    const unit = {unit_json};
    const xKey = {x_key_json};
    const yKey = {y_key_json};
    const seriesKey = {series_key_json};
    const rows = {rows_json};
    const seriesList = {series_list_json};
    const xList = {x_list_json};
    const bgmDataUri = {bgm_data_uri_json};
    const bgmFilename = {bgm_filename_json};

    const playBtn = document.getElementById('playBtn');
    const speedBtn = document.getElementById('speedBtn');
    const timelineRange = document.getElementById('timelineRange');
    const sliderProgress = document.getElementById('sliderProgress');
    const startLabel = document.getElementById('startLabel');
    const endLabel = document.getElementById('endLabel');
    const musicBtn = document.getElementById('musicBtn');
    const bgmAudio = document.getElementById('bgmAudio');

    const speedPresets = [
      {{ label: '0.5x', interval: 1200 }},
      {{ label: '1x', interval: 700 }},
      {{ label: '2x', interval: 350 }}
    ];

    function showError(message) {{
      chartDom.style.display = 'none';
      document.getElementById('timelineBar').style.display = 'none';
      errorBox.style.display = 'block';
      errorBox.textContent = '渲染失败：' + message;
    }}

    function formatValue(value) {{
      if (value === null || value === undefined || value === '') return '-';
      return `${{value}}${{unit}}`;
    }}

    function formatDateParts(value) {{
      if (!value) return {{ md: '', yy: '' }};
      const s = String(value);
      const m = s.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/);
      if (m) {{
        return {{ md: `${{m[2]}}-${{m[3]}}`, yy: m[1] }};
      }}
      return {{ md: s, yy: '' }};
    }}

    function setTimeLabel(el, value) {{
      const parts = formatDateParts(value);
      el.innerHTML = `<span class="md">${{parts.md}}</span><span class="yy">${{parts.yy}}</span>`;
    }}

    function isCompactLayout() {{
      return window.innerWidth <= 768;
    }}

    function rowValueToNumber(value) {{
      if (value === null || value === undefined || value === '') return null;
      const num = Number(value);
      return Number.isFinite(num) ? num : null;
    }}

    const colorPalette = [
      {{ line: '#18e0b5', areaTop: 'rgba(24, 224, 181, 0.20)', areaBottom: 'rgba(24, 224, 181, 0)' }},
      {{ line: '#4c97ff', areaTop: 'rgba(76, 151, 255, 0.18)', areaBottom: 'rgba(76, 151, 255, 0)' }},
      {{ line: '#9b6bff', areaTop: 'rgba(155, 107, 255, 0.18)', areaBottom: 'rgba(155, 107, 255, 0)' }},
      {{ line: '#f59e0b', areaTop: 'rgba(245, 158, 11, 0.18)', areaBottom: 'rgba(245, 158, 11, 0)' }},
      {{ line: '#ec4899', areaTop: 'rgba(236, 72, 153, 0.18)', areaBottom: 'rgba(236, 72, 153, 0)' }}
    ];

    const fullSeriesDataMap = {{}};
    seriesList.forEach((seriesName) => {{
      fullSeriesDataMap[seriesName] = xList.map((xValue) => {{
        const found = rows.find(row => row[seriesKey] === seriesName && row[xKey] === xValue);
        return found ? rowValueToNumber(found[yKey]) : null;
      }});
    }});

    let currentIndex = Math.max(0, xList.length - 1);
    let speedPresetIndex = 1;
    let currentInterval = speedPresets[speedPresetIndex].interval;
    let timer = null;
    let isPlaying = false;

    let isMusicOn = false;
    let hasMusic = false;
    let audioUnlocked = false;

    timelineRange.max = Math.max(0, xList.length - 1);
    timelineRange.value = currentIndex;
    setTimeLabel(startLabel, xList[0] || '');
    setTimeLabel(endLabel, xList[xList.length - 1] || '');

    function updateSliderProgress() {{
      const max = Number(timelineRange.max) || 1;
      const val = Number(timelineRange.value) || 0;
      const pct = max === 0 ? 0 : (val / max) * 100;
      sliderProgress.style.width = pct + '%';
    }}

    function getSafeIndex() {{
      if (!xList.length) return 0;
      return Math.min(Math.max(currentIndex, 0), xList.length - 1);
    }}

    function getCurrentTimeText() {{
      if (!xList || !xList.length) return '';
      return xList[getSafeIndex()] || '';
    }}

    function getLastValidPoint(partialData) {{
      for (let i = partialData.length - 1; i >= 0; i--) {{
        const val = partialData[i];
        if (val !== null && val !== undefined && val !== '') {{
          return {{ index: i, value: val }};
        }}
      }}
      return null;
    }}

    function buildSeries(endIndex) {{
      const animDuration = isPlaying ? currentInterval : 260;
      const animEasing = isPlaying ? 'linear' : 'cubicOut';

      return seriesList.map((seriesName, index) => {{
        const theme = colorPalette[index % colorPalette.length];
        const fullData = fullSeriesDataMap[seriesName] || [];
        const partialData = fullData.slice(0, endIndex + 1);
        const lastPoint = getLastValidPoint(partialData);

        return {{
          name: seriesName,
          type: 'line',
          smooth: true,
          showSymbol: false,
          connectNulls: false,
          symbol: 'circle',
          symbolSize: 6,
          data: partialData,
          animation: true,
          animationDuration: animDuration,
          animationEasing: animEasing,
          animationDurationUpdate: animDuration,
          animationEasingUpdate: animEasing,
          itemStyle: {{ color: theme.line, borderWidth: 0 }},
          lineStyle: {{
            width: isCompactLayout() ? 3.5 : 4,
            color: theme.line
          }},
          areaStyle: {{
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {{ offset: 0, color: theme.areaTop }},
              {{ offset: 1, color: theme.areaBottom }}
            ])
          }},
          markPoint: lastPoint ? {{
            symbol: 'circle',
            symbolSize: 8,
            itemStyle: {{ color: theme.line, borderWidth: 0 }},
            label: {{ show: false }},
            data: [{{ coord: [lastPoint.index, lastPoint.value] }}]
          }} : undefined
        }};
      }});
    }}

    function buildCenterTimeGraphic() {{
      const compact = isCompactLayout();
      return {{
        type: 'text',
        left: 'center',
        top: '47%',
        silent: true,
        z: 1,
        style: {{
          text: getCurrentTimeText(),
          fill: compact ? 'rgba(148, 163, 184, 0.14)' : 'rgba(148, 163, 184, 0.16)',
          fontSize: compact ? 32 : 38,
          fontWeight: 700,
          textAlign: 'center',
          textVerticalAlign: 'middle'
        }}
      }};
    }}

    function buildRightLabelsGraphics(endIndex) {{
      const graphics = [];
      const points = [];
      const compact = isCompactLayout();

      seriesList.forEach((seriesName, index) => {{
        const theme = colorPalette[index % colorPalette.length];
        const fullData = fullSeriesDataMap[seriesName] || [];
        const partialData = fullData.slice(0, endIndex + 1);
        const lastPoint = getLastValidPoint(partialData);
        if (!lastPoint) return;

        const pixel = chart.convertToPixel({{ xAxisIndex: 0, yAxisIndex: 0 }}, [lastPoint.index, lastPoint.value]);
        if (!pixel || !Array.isArray(pixel) || !isFinite(pixel[0]) || !isFinite(pixel[1])) return;

        points.push({{
          seriesName,
          color: theme.line,
          value: lastPoint.value,
          x: pixel[0],
          y: pixel[1]
        }});
      }});

      if (!points.length) return graphics;

      points.sort((a, b) => a.y - b.y);

      const minGap = compact ? 22 : 24;
      for (let i = 1; i < points.length; i++) {{
        if (points[i].y - points[i - 1].y < minGap) {{
          points[i].y = points[i - 1].y + minGap;
        }}
      }}

      const leftLimit = compact ? 16 : 20;
      const labelGap = 10;

      points.forEach(item => {{
        const text = `${{item.seriesName}}  ${{formatValue(item.value)}}`;
        const anchorX = Math.max(item.x - labelGap, leftLimit);

        graphics.push({{
          type: 'text',
          x: anchorX,
          y: item.y,
          silent: true,
          z: 20,
          style: {{
            text: text,
            fill: '#f8fafc',
            backgroundColor: 'rgba(15, 23, 42, 0.68)',
            borderColor: item.color,
            borderWidth: 1.2,
            borderRadius: 999,
            padding: compact ? [4, 9] : [4, 10],
            fontSize: compact ? 12 : 13,
            fontWeight: 700,
            textAlign: 'right',
            textVerticalAlign: 'middle',
            shadowBlur: 8,
            shadowColor: 'rgba(0,0,0,0.18)'
          }}
        }});
      }});

      return graphics;
    }}

    function renderChart() {{
      if (!xList.length || !seriesList.length) {{
        throw new Error('没有可用于渲染折线图的数据');
      }}

      const compact = isCompactLayout();
      const safeIndex = getSafeIndex();
      const animDuration = isPlaying ? currentInterval : 260;
      const animEasing = isPlaying ? 'linear' : 'cubicOut';

      chart.setOption({{
        backgroundColor: 'transparent',
        color: colorPalette.map(c => c.line),
        animation: true,
        animationDuration: animDuration,
        animationEasing: animEasing,
        animationDurationUpdate: animDuration,
        animationEasingUpdate: animEasing,
        title: {{
          text: title,
          left: compact ? 16 : 20,
          top: compact ? 14 : 18,
          textStyle: {{
            color: '#f8fafc',
            fontSize: compact ? 16 : 18,
            fontWeight: 700
          }}
        }},
        legend: {{
          data: seriesList,
          top: compact ? 42 : 46,
          left: compact ? 16 : 20,
          itemWidth: compact ? 14 : 16,
          itemHeight: 4,
          icon: 'roundRect',
          textStyle: {{
            color: '#a7b5c9',
            fontSize: compact ? 11 : 12,
            padding: [0, 0, 0, 5]
          }}
        }},
        tooltip: {{
          trigger: 'axis',
          confine: true,
          backgroundColor: 'rgba(15, 23, 42, 0.94)',
          borderColor: '#334155',
          borderWidth: 1,
          padding: [10, 12],
          textStyle: {{ color: '#f1f5f9' }},
          position: function(point, params, dom, rect, size) {{
            const viewWidth = size && size.viewSize ? size.viewSize[0] : chart.getWidth();
            const contentWidth = size && size.contentSize ? size.contentSize[0] : 220;
            const leftFixedX = compact ? 16 : 20;
            const rightFixedX = Math.max(leftFixedX, viewWidth - contentWidth - leftFixedX);
            const topFixedY = compact ? 70 : 76;
            const pointerX = Array.isArray(point) ? point[0] : viewWidth / 2;
            if (pointerX <= viewWidth / 2) return [rightFixedX, topFixedY];
            return [leftFixedX, topFixedY];
          }},
          axisPointer: {{
            type: 'line',
            lineStyle: {{
              color: 'rgba(148, 163, 184, 0.48)',
              type: 'dashed',
              width: 1
            }}
          }},
          formatter: function(params) {{
            if (!params || !params.length) return '';
            const axisValue = params[0].axisValue;
            let html = `<div style="margin-bottom:8px;font-size:13px;font-weight:700;color:#f8fafc;">${{axisValue}}</div>`;
            params.forEach(item => {{
              const marker = item.marker || '';
              const name = item.seriesName || '';
              const value = Array.isArray(item.value) ? item.value[item.value.length - 1] : item.value;
              html += `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;font-size:12px;gap:16px;">
                  <span style="display:flex;align-items:center;">
                    ${{marker}}<span style="color:#cbd5e1;">${{name}}</span>
                  </span>
                  <span style="font-weight:700;color:#f8fafc;">${{formatValue(value)}}</span>
                </div>`;
            }});
            return html;
          }}
        }},
        grid: {{
          left: compact ? 16 : 20,
          right: compact ? 12 : 16,
          top: compact ? 74 : 80,
          bottom: compact ? 78 : 82,
          containLabel: true
        }},
        xAxis: {{
          type: 'category',
          boundaryGap: false,
          data: xList.slice(0, safeIndex + 1),
          axisLine: {{
            lineStyle: {{ color: 'rgba(71, 85, 105, 0.45)' }}
          }},
          axisTick: {{ show: false }},
          axisLabel: {{ show: false }},
          splitLine: {{ show: false }}
        }},
        yAxis: {{
          type: 'value',
          position: 'right',
          scale: true,
          splitNumber: 5,
          axisLine: {{ show: false }},
          axisTick: {{ show: false }},
          axisLabel: {{
            color: '#8ea1bc',
            margin: 6,
            fontSize: compact ? 10 : 11,
            formatter: function(value) {{
              return formatValue(value);
            }}
          }},
          splitLine: {{
            show: true,
            lineStyle: {{
              color: 'rgba(56, 104, 190, 0.16)',
              type: 'dashed',
              width: 1
            }}
          }}
        }},
        graphic: [buildCenterTimeGraphic()],
        series: buildSeries(safeIndex)
      }}, true);

      chart.setOption({{
        graphic: [
          buildCenterTimeGraphic(),
          ...buildRightLabelsGraphics(safeIndex)
        ]
      }});

      timelineRange.value = safeIndex;
      updateSliderProgress();
    }}

    function setPlayButtonState() {{
      playBtn.textContent = isPlaying ? '❚❚' : '▶';
    }}

    function updateSpeedButtonState() {{
      speedBtn.textContent = speedPresets[speedPresetIndex].label;
      speedBtn.title = `当前播放速度：${{speedPresets[speedPresetIndex].label}}`;
    }}

    function stopTimer() {{
      if (timer) {{
        clearInterval(timer);
        timer = null;
      }}
    }}

    function getMusicOnIcon() {{
      return `
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M14.5 4.5a1 1 0 0 1 1.7.7v13.6a1 1 0 0 1-1.7.7l-4.7-4.5H6a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2h3.8l4.7-4.5Z"></path>
          <path d="M18.2 9.1a1 1 0 0 1 1.4 0 5 5 0 0 1 0 7.1 1 1 0 0 1-1.4-1.4 3 3 0 0 0 0-4.3 1 1 0 0 1 0-1.4Z"></path>
        </svg>
      `;
    }}

    function getMusicOffIcon() {{
      return `
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M14.5 4.5a1 1 0 0 1 1.7.7v13.6a1 1 0 0 1-1.7.7l-4.7-4.5H6a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2h3.8l4.7-4.5Z"></path>
          <path d="M18 9l-4 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"></path>
          <path d="M14 9l4 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"></path>
        </svg>
      `;
    }}

    function updateMusicButtonState() {{
      if (!musicBtn) return;

      if (!hasMusic) {{
        musicBtn.classList.remove('on', 'off');
        musicBtn.classList.add('disabled');
        musicBtn.disabled = true;
        musicBtn.title = '未找到背景音乐';
        musicBtn.innerHTML = getMusicOffIcon();
        return;
      }}

      musicBtn.disabled = false;
      musicBtn.classList.remove('disabled');
      musicBtn.classList.toggle('on', isMusicOn);
      musicBtn.classList.toggle('off', !isMusicOn);
      musicBtn.title = isMusicOn
        ? `背景音乐已开启${{bgmFilename ? '：' + bgmFilename : ''}}`
        : `背景音乐已关闭${{bgmFilename ? '：' + bgmFilename : ''}}`;
      musicBtn.innerHTML = isMusicOn ? getMusicOnIcon() : getMusicOffIcon();
    }}

    function initBackgroundMusic() {{
      hasMusic = !!bgmDataUri;
      if (!hasMusic) {{
        updateMusicButtonState();
        return;
      }}

      bgmAudio.src = bgmDataUri;
      bgmAudio.volume = 0.55;
      bgmAudio.muted = true;
      bgmAudio.pause();
      bgmAudio.currentTime = 0;
      isMusicOn = false;
      audioUnlocked = false;
      updateMusicButtonState();
    }}

    function stopBackgroundMusic(resetToStart = true) {{
      if (!hasMusic) return;
      bgmAudio.pause();
      bgmAudio.muted = true;
      if (resetToStart) {{
        try {{
          bgmAudio.currentTime = 0;
        }} catch (err) {{
          console.error('背景音乐重置失败', err);
        }}
      }}
    }}

    async function unlockAudioByGesture() {{
      if (!hasMusic || audioUnlocked) return;

      try {{
        bgmAudio.muted = true;
        bgmAudio.currentTime = 0;
        await bgmAudio.play();
        bgmAudio.pause();
        bgmAudio.currentTime = 0;
        audioUnlocked = true;
      }} catch (err) {{
        console.error('背景音乐解锁失败', err);
      }}
    }}

    async function startBackgroundMusicFromBeginning() {{
      if (!hasMusic || !isMusicOn) return;

      try {{
        await unlockAudioByGesture();
        bgmAudio.pause();
        bgmAudio.currentTime = 0;
        bgmAudio.muted = false;
        await bgmAudio.play();
      }} catch (err) {{
        console.error('背景音乐播放失败', err);
        stopBackgroundMusic(true);
      }}
    }}

    async function toggleMusic() {{
      if (!hasMusic) return;

      if (isMusicOn) {{
        isMusicOn = false;
        stopBackgroundMusic(true);
        updateMusicButtonState();
        return;
      }}

      isMusicOn = true;
      updateMusicButtonState();

      await unlockAudioByGesture();

      if (!isPlaying) {{
        stopBackgroundMusic(true);
        return;
      }}

      await startBackgroundMusicFromBeginning();
    }}

    function startTimer() {{
      stopTimer();
      timer = setInterval(() => {{
        if (currentIndex >= xList.length - 1) {{
          currentIndex = xList.length - 1;
          isPlaying = false;
          setPlayButtonState();
          stopTimer();
          stopBackgroundMusic(true);
          renderChart();
          return;
        }}
        currentIndex += 1;
        renderChart();
      }}, currentInterval);
    }}

    speedBtn.addEventListener('click', function() {{
      speedPresetIndex = (speedPresetIndex + 1) % speedPresets.length;
      currentInterval = speedPresets[speedPresetIndex].interval;
      updateSpeedButtonState();
      if (isPlaying) startTimer();
    }});

    if (musicBtn) {{
      musicBtn.addEventListener('click', async function() {{
        await toggleMusic();
      }});
    }}

    playBtn.addEventListener('click', async function() {{
      if (xList.length <= 1) return;

      if (isPlaying) {{
        isPlaying = false;
        setPlayButtonState();
        stopTimer();
        stopBackgroundMusic(true);
        renderChart();
      }} else {{
        if (currentIndex >= xList.length - 1) currentIndex = 0;
        isPlaying = true;
        setPlayButtonState();
        if (isMusicOn) {{
          await startBackgroundMusicFromBeginning();
        }}
        startTimer();
      }}
    }});

    timelineRange.addEventListener('input', function(e) {{
      currentIndex = Number(e.target.value) || 0;
      isPlaying = false;
      setPlayButtonState();
      stopTimer();
      stopBackgroundMusic(true);
      renderChart();
    }});

    timelineRange.addEventListener('change', function(e) {{
      currentIndex = Number(e.target.value) || 0;
      isPlaying = false;
      setPlayButtonState();
      stopTimer();
      stopBackgroundMusic(true);
      renderChart();
    }});

    try {{
      initBackgroundMusic();
      renderChart();
      setPlayButtonState();
      updateSpeedButtonState();
      updateSliderProgress();
    }} catch (err) {{
      console.error(err);
      showError(err && err.message ? err.message : String(err));
    }}

    window.addEventListener('resize', () => {{
      try {{
        chart.resize();
        renderChart();
      }} catch (err) {{
        console.error(err);
      }}
    }});
  </script>
</body>
</html>"""
    return html
