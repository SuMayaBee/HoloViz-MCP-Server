# AGENTS.md - HoloViz MCP App

A guide for AI coding agents to contribute to the HoloViz MCP App project.

---

## Repository Overview

**Project**: HoloViz MCP App — MCP server for creating interactive HoloViz visualizations inside LLM chat
**Language**: Python 3.11+
**Build System**: Pixi (conda-based) + Hatchling (PEP 517)
**Framework**: FastMCP 3.0+ (server composition via `mount()`)
**Key Dependencies**: Panel, HoloViews, hvPlot, Bokeh, Pydantic, psutil, ruff

---

## Quick Start

```bash
# 1. Install Pixi
curl -fsSL https://pixi.sh/install.sh | bash

# 2. Install environment
cd holoviz-mcp-app
pixi install

# 3. Install in editable mode
pixi run postinstall

# 4. Verify
hvmcp --help
```

---

## Architecture

### Three Layers

1. **MCP Server Layer** (FastMCP) — tools AI agents call
2. **Display Server Layer** (Panel subprocess) — renders visualizations
3. **MCP App Resources** (HTML templates) — rich UIs in LLM chat iframes

### Module Structure

```
src/holoviz_mcp_app/
├── __init__.py          # Package init
├── cli.py               # Typer CLI: serve, mcp, status
├── config.py            # Pydantic config + env var detection
│
├── display/             # Panel subprocess system
│   ├── app.py           # Panel server entry point
│   ├── manager.py       # PanelServerManager lifecycle
│   ├── client.py        # DisplayClient (HTTP to /api/snippet)
│   ├── database.py      # SQLite + FTS5 persistence
│   ├── endpoints.py     # Tornado handlers
│   ├── validation.py    # 5-layer validation pipeline
│   ├── utils.py         # execute_in_module, find_extensions
│   └── pages/           # Web UI pages
│       ├── view_page.py
│       ├── feed_page.py
│       ├── add_page.py
│       └── admin_page.py
│
├── templates/           # MCP App HTML (iframes in LLM chat)
│   ├── show.html        # Chart viewer + click events
│   ├── dashboard.html   # Chart + stats + filters
│   ├── stream.html      # Live streaming + play/pause
│   └── multi.html       # Multi-chart grid
│
├── server/              # MCP server composition
│   ├── main.py          # Main server + core tools
│   ├── compose.py       # Mount all sub-servers
│   ├── panel_mcp.py     # pn.* tools
│   ├── hvplot_mcp.py    # hvplot.* tools
│   └── holoviews_mcp.py # hv.* tools
│
├── guided/              # High-level tools (config → codegen → show)
│   ├── server.py        # viz.* sub-server
│   └── codegen.py       # Code generators per chart type
│
├── core/                # Pure Python business logic
│   ├── pn.py            # Panel introspection
│   ├── hvplot.py        # hvPlot discovery
│   ├── hv.py            # HoloViews discovery
│   └── skills.py        # Skill file loading
│
└── skills/              # Agent skill files (SKILL.md)
    ├── panel/
    ├── hvplot/
    ├── holoviews/
    ├── param/
    └── data/
```

### Server Composition

The main server mounts four sub-servers with namespaces:

```python
main_mcp.mount(guided_mcp, namespace="viz")       # viz.create, viz.dashboard, etc.
main_mcp.mount(panel_mcp, namespace="pn")          # pn.list, pn.get, pn.params
main_mcp.mount(hvplot_mcp, namespace="hvplot")      # hvplot.list, hvplot.get
main_mcp.mount(holoviews_mcp, namespace="hv")       # hv.list, hv.get
```

Core tools on main server: `show`, `stream`, `load_data`, `handle_interaction`, `validate`, `skill_list`, `skill_get`, `list_packages`.

### Data Flow

```
LLM calls show(code)
  → MCP server validates code (5-layer pipeline)
  → DisplayClient POSTs to /api/snippet
  → Panel subprocess executes code
  → SQLite stores snippet with metadata
  → URL returned to LLM
  → MCP App HTML embeds Panel URL in iframe
  → User clicks chart → JS calls app.callServerTool("handle_interaction")
  → Server computes insight → returned to iframe
```

### Validation Pipeline (5 layers)

1. **Syntax** — `ast.parse(code)`
2. **Security** — ruff + blocked imports (subprocess, socket, ctypes, etc.)
3. **Packages** — `importlib.util.find_spec()` for all imports
4. **Extensions** — detect Panel extensions (plotly, vega, deckgl)
5. **Runtime** — execute in isolated `types.ModuleType` namespace

---

## Key Technical Decisions

### MCP Apps (templates/)

Every visualization tool returns an MCP App resource — an HTML file using `@modelcontextprotocol/ext-apps` SDK. The iframe communicates back to the server via `app.callServerTool()`.

### Bidirectional Click Events

Bokeh TapTool + CustomJS dispatches `bokeh-tap` events. The HTML template catches them and calls `app.callServerTool("handle_interaction", ...)`. The server computes insights and returns text.

### Guided Tools vs show()

`show(code)` runs arbitrary Python. `viz.create(kind, data, x, y)` is a convenience wrapper that calls `codegen.py` to generate Python, then delegates to `show`. Guided tools inherit validation, persistence, and web UI for free.

### Display Server Startup

`app_lifespan` (async context manager) eagerly starts the Panel subprocess, checks for stale processes, waits for `/api/health`, and registers cleanup on exit.

---

## Configuration

Environment variables (prefix `HOLOVIZ_MCP_APP_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOLOVIZ_MCP_APP_PORT` | 5077 | Panel server port |
| `HOLOVIZ_MCP_APP_HOST` | localhost | Panel server host |
| `HOLOVIZ_MCP_APP_MAX_RESTARTS` | 3 | Max restart attempts |
| `HOLOVIZ_MCP_APP_DB_PATH` | snippets.db | SQLite database path |
| `HOLOVIZ_MCP_APP_EXTERNAL_URL` | (auto) | Public URL override |
| `HOLOVIZ_MCP_APP_SKILLS_DIR` | (builtin) | Custom skills directory |

Auto-detection: JupyterHub (`JUPYTERHUB_SERVICE_PREFIX`) and Codespaces (`CODESPACE_NAME`).

---

## CLI Commands

```bash
hvmcp serve        # Start Panel display server
hvmcp mcp          # Start MCP server (stdio transport)
hvmcp status       # Check display server health
```

---

## Development Workflow

```bash
# Run tests
pixi run test

# Lint
pixi run lint

# Format
pixi run format

# Install editable
pixi run postinstall
```

### Adding a New MCP Tool

1. Choose the right sub-server or add to `server/main.py`
2. Add tool with `@mcp.tool()` decorator
3. Add tests
4. If guided tool: add codegen function in `guided/codegen.py`

### Adding a New Skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter
2. The skills system auto-discovers it at runtime

---

## Code Quality

- **Type hints**: Required for all new code (Python 3.11+ syntax)
- **Linting**: ruff (formatting + linting + isort)
- **Line length**: 120 characters
- **Imports**: Single-line, alphabetical

---

## Dependencies

Core runtime:
- `fastmcp>=3.0` — MCP server framework
- `panel` — Web framework + display server
- `holoviews` — Declarative visualization
- `hvplot` — High-level plotting API
- `bokeh` — Rendering backend
- `pandas` — DataFrames
- `pydantic` — Configuration models
- `psutil` — Process management
- `requests` — HTTP client
- `typer` — CLI framework
- `ruff` — Code validation

---

**Last Updated**: 2026-03-18
