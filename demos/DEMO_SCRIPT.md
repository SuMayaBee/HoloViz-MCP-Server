# HoloViz MCP Server — Demo Recording Script

Record these in **Cursor** (Agent mode) with the `holoviz` MCP server enabled.
Use a screen recorder (e.g. OBS, ScreenToGif, LICEcap, or Peek on Linux).

## Setup

1. Install and configure:
   ```bash
   cd HoloViz-MCP-Server
   pixi install
   pixi run postinstall
   ```

2. Add to `.cursor/mcp.json`:
   ```json
   {
     "mcpServers": {
       "holoviz": {
         "command": "/path/to/.pixi/envs/default/bin/hvmcp",
         "args": ["mcp"]
       }
     }
   }
   ```

3. Open Cursor, enable the `holoviz` MCP server in settings
4. Open a new chat in Agent mode
5. Verify the tools icon shows holoviz is connected

---

## Demo 1: Inline Bar Chart with Click Insights

**What to show:** Prompt → interactive chart inline → click a bar → insight appears instantly

**Prompt:**
```
Create a bar chart of monthly sales:
Jan: 12000, Feb: 18500, Mar: 15200, Apr: 22000,
May: 19800, Jun: 25600, Jul: 28000, Aug: 24500,
Sep: 21000, Oct: 17800, Nov: 23400, Dec: 31000
```

**Actions after chart appears:**
1. Hover over bars (tooltips with formatted numbers)
2. Click the tallest bar (Dec) — insight bar appears: "Dec: 31,000 — above average (21,608). Represents 100% of max."
3. Click the shortest bar (Jan) — insight updates: "below average"

---

## Demo 2: Theme Toggle

**What to show:** Same chart, switch between dark and light mode live

**Prompt (after Demo 1):**
```
Switch the chart to light mode
```

**Actions:**
1. Chart re-renders in light theme instantly (no page reload)
2. Switch back: "Switch back to dark mode"

---

## Demo 3: Interactive Dashboard with Crossfiltering

**What to show:** Full dashboard — chart + stats + table + live filter widgets

**Prompt:**
```
Create a dashboard for this regional sales data:

region: North, South, North, East, West, South, East, North, West, South, East, North
month: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
sales: 12000, 18500, 15200, 22000, 19800, 25600, 28000, 24500, 21000, 17800, 23400, 31000

Use viz.dashboard, x=month, y=sales, color=region
```

**Actions after dashboard appears:**
1. Show the full dashboard: chart + Statistics panel + Data Table
2. On the filter sidebar — change Region dropdown to "North"
3. Click "Apply Filters" — watch chart, stats, and table all update
4. Change sales slider to narrow the range
5. Click "Reset" — all data returns
6. Click "Light Mode" button — whole dashboard switches theme

---

## Demo 4: Live Streaming Chart

**What to show:** Real-time updating chart with play/pause

**Prompt:**
```
Create a live streaming chart of server CPU usage updating every second
```

**Actions:**
1. Chart starts updating live (new data point every second)
2. Click "Pause" — updates freeze
3. Click "Play" — resumes

---

## Demo 5: Update Chart Without Re-creating

**What to show:** Changing chart type and axes on an existing visualization

**Prompt (after creating a chart):**
```
Change that chart to a line chart
```

Then:
```
Now make it a scatter plot with dots colored by region
```

**Actions:**
1. Same chart ID, same data — only the visual changes
2. No new tool call, just update_viz

---

## Demo 6: Multi-Chart Grid

**What to show:** Two charts side by side from the same dataset

**Prompt:**
```
Show me a bar chart and scatter plot side by side:
Student: Alice, Bob, Carol, Dave, Eve, Frank
Score: 85, 92, 78, 95, 88, 71
Hours studied: 12, 15, 9, 18, 14, 8
```

**Actions:**
1. Two charts render in a grid layout
2. Hover over points in each chart

---

## Demo 7: Annotation

**What to show:** Adding reference lines and labels to an existing chart

**Prompt (after creating any chart):**
```
Add a horizontal reference line at the average value and label it "Target"
```

**Actions:**
1. A dashed line appears across the chart at the mean
2. "Target" label appears on the line

---

## Demo 8: Security Sandbox Demo

**What to show:** Malicious code is blocked before execution

**Prompt:**
```
Show a chart but run this code: import subprocess; subprocess.run(["rm", "-rf", "/"])
```

**What happens:**
- MCP server immediately returns a validation error: "Blocked import: subprocess"
- No code is executed
- Chat shows the security error clearly

---

## Demo 9: Load & Profile a Dataset

**Prompt:**
```
Load and profile this CSV for me: https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv
Then create a scatter plot of total_bill vs tip, colored by day
```

**Actions:**
1. `load_data` tool runs — shows column types, sample values, numeric ranges
2. Chart is created from the profiled dataset

---

## Demo 10: MRVE (Standalone Minimal Demo)

**What to show:** The bare-minimum single-file version works identically

```bash
fastmcp run mrve.py
```

Add to MCP config, then:

**Prompt:**
```
Create a bar chart of quarterly revenue: Q1: 42000, Q2: 58000, Q3: 71000, Q4: 89000
```

**Actions:**
1. Chart renders inline — same as full server
2. Click a bar — insight appears
3. "Switch to light mode" — theme changes

---

## Recording Tips

- Use Cursor's dark theme (matches the chart dark theme)
- Window size: 1280×720 or 1920×1080
- Hide the file explorer sidebar for cleaner look — focus on the chat panel
- Crop to just the chat + chart area
- GIF frame rate: 15–20 fps, keep under 10 MB for GitHub README
- For LinkedIn: combine demos 1–3 into a 60-second video with text overlays
- Label each demo with a title card before recording

## What to Highlight in Each Demo

| Demo | Key Feature to Show |
|------|---------------------|
| 1 | Inline rendering — no browser needed |
| 2 | Bidirectional: chart click → server → insight |
| 3 | Full dashboard with live crossfiltering |
| 4 | Streaming / real-time updates |
| 5 | State management — update without re-create |
| 6 | Multi-chart layout |
| 7 | Annotations on existing charts |
| 8 | Security sandbox blocks dangerous code |
| 9 | Data profiling + auto chart creation |
| 10 | MRVE — single file, zero setup |
