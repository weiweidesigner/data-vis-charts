# Data Vis Charts

Aime Chart 通用数据可视化组件库，包含 16 个独立 Python 组件与 16 份 Schema。输入结构化数据，输出可嵌入的 HTML，保留原组件样式、交互和 CLI。

## 安装与使用

建议 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 先阅读组件的数据契约
cat app/skills/generic-chart/schemas/bar_chart.schema.json

# 使用离线样例生成图表
python app/skills/generic-chart/scripts/bar_chart.py --payload examples/bar.json --output outputs/bar.html
python app/skills/generic-chart/scripts/dynamic_line.py --payload examples/dynamic_line.json --output outputs/dynamic-line.html
```

生成 HTML 可在浏览器打开或通过 iframe 嵌入。部分图表使用 CDN 上的 ECharts、D3、Mermaid 或字体，首次显示需要网络。动态折线的 Python 渲染器及音乐资源已内置，无需本机 Codex Skill。

基础图表的暗夜模式遵循 StreamViz 语义色板：透明图表背景、`#f1f5f9` 主文字、`#c1cad7` 次文字、`#2b3544` 弱分隔线，以及适合暗色背景的高明度系列色。组件接受 payload 中的 `theme: "dark"` / `themeMode: "dark"`，也会响应宿主 URL 的 `?theme=dark`。

## 组件

| 类型 | 脚本 |
| --- | --- |
| 柱状图 | `bar_chart.py` |
| 柱折图 | `bar_line.py` |
| 单折线 / 多折线 | `line_chart.py` / `group_line.py` |
| 分组柱状图 | `grouped_bar.py` |
| 饼图 / 双环图 | `pie.py` / `double_ring_pie.py` |
| 瀑布图 / 矩形树图 | `waterfall.py` / `treemap.py` |
| 动态折线 / 柱状 / 气泡 | `dynamic_line.py` / `dynamic_bar.py` / `dynamic_bubble.py` |
| 脑图 / 流程图 | `mind_map.py` / `flowchart.py` |
| 旅程图 / 时间线 | `journey.py` / `timeline.py` |

每个组件的参数以 `--help` 和对应 `schemas/*.schema.json` 为准；部分组件也支持 `--schema`。组件调用规范见 `app/skills/generic-chart/SKILL.md`。

## 目录与来源

- `app/skills/generic-chart/scripts/`：组件实现。
- `app/skills/generic-chart/schemas/`：字段、视觉通道及 payload 契约。
- `app/skills/generic-chart/runtime/`：动态折线所需的 Aime 渲染器、工具和资源。
- `examples/`：合成的离线输入数据。
- `tests/`：事件标签及独立运行回归验证。

组件来自 Aime Chart 项目的通用图表目录。饼图、瀑布图、双环图与业务组件库共享实现，此仓库保存当前源码副本。通用 K 线沿用业务图表库内核，未在此复制；需要宿主另外配置业务组件库。

## 验证

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```
