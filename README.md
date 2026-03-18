# HoloViz MCP App

An MCP server for the HoloViz ecosystem. Lets AI agents (Claude, Copilot, Cursor) create interactive visualizations and dashboards that render as live UIs directly inside LLM chat via MCP Apps.

Built on Panel, HoloViews, hvPlot, and FastMCP.

---

## Features

- **`show(code)`** — Execute any Python visualization code, get a live interactive URL back
- **`viz.create`** — High-level guided tool: describe a chart, get it rendered (no Python needed)
- **`viz.dashboard`** — Create multi-chart dashboards from structured config
- **`stream(code)`** — True server-side streaming with `pn.state.add_periodic_callback()`
- **`load_data`** — Profile any dataset (CSV, Parquet, Zarr, S3, etc.)
- **`pn.*` / `hvplot.*` / `hv.*`** — Introspect Panel components, hvPlot chart types, HoloViews elements
- **`skill_list` / `skill_get`** — Access best-practice guides for Panel, hvPlot, HoloViews, Param
- **5-layer validation** — syntax → security → packages → extensions → runtime, before any code runs
- **SQLite persistence** — every visualization stored permanently with full-text search
- **MCP Apps** — inline iframe rendering in Claude Desktop and VS Code Insiders

---

## Requirements

- Python 3.11+
- [Pixi](https://pixi.sh) — conda-based environment manager

---

## Setup

### 1. Install Pixi

```bash
curl -fsSL https://pixi.sh/install.sh | bash
source ~/.bashrc
```

### 2. Clone and install

```bash
git clone <your-repo-url>
cd holoviz-mcp-app

pixi install
pixi run postinstall
```

### 3. Verify

```bash
hvmcp --help
```

---

## Usage

### Start the display server

```bash
hvmcp serve
```

Starts the Panel server at `http://127.0.0.1:5077`. Web UI pages:

| Page | URL |
|------|-----|
| Live feed | `http://127.0.0.1:5077/feed` |
| Add visualization | `http://127.0.0.1:5077/add` |
| Admin | `http://127.0.0.1:5077/admin` |

### Start the MCP server

In a second terminal:

```bash
hvmcp mcp
```

---

## MCP Client Configuration

### VS Code (Insiders — supports inline rendering)

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "holoviz": {
      "type": "stdio",
      "command": "/path/to/holoviz-mcp-app/.pixi/envs/default/bin/hvmcp",
      "args": ["mcp"]
    }
  }
}
```

> Replace `/path/to/holoviz-mcp-app` with your actual path.

### Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "holoviz": {
      "command": "/path/to/holoviz-mcp-app/.pixi/envs/default/bin/hvmcp",
      "args": ["mcp"]
    }
  }
}
```

### Cursor

Create `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "holoviz": {
      "command": "/path/to/holoviz-mcp-app/.pixi/envs/default/bin/hvmcp",
      "args": ["mcp"]
    }
  }
}
```

---

## Example Prompts

```
Create a bar chart of random sales data by category
```
```
Create a line chart showing a sine wave
```
```
Load this CSV and create a visualization: /path/to/data.csv
```
```
Create a live streaming chart that updates every second
```
```
What Panel widgets are available?
```

---

## Project Structure

```
src/holoviz_mcp_app/
├── cli.py              # CLI entry point (hvmcp)
├── config.py           # Pydantic config + env vars
├── display/            # Panel subprocess (server, DB, validation)
├── server/             # MCP server + tools
├── guided/             # High-level viz tools + code generators
├── core/               # Panel/hvPlot/HoloViews introspection
├── templates/          # MCP App HTML (inline rendering)
└── skills/             # Best-practice guides (SKILL.md files)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOLOVIZ_MCP_APP_PORT` | `5077` | Panel server port |
| `HOLOVIZ_MCP_APP_HOST` | `127.0.0.1` | Panel server host |
| `HOLOVIZ_MCP_APP_EXTERNAL_URL` | — | Public URL (for JupyterHub/Codespaces) |
| `HOLOVIZ_MCP_APP_DB_PATH` | `~/.holoviz-mcp-app/snippets/snippets.db` | SQLite database path |

---

## License

BSD 3-Clause
