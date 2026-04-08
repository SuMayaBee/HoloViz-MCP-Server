# AGENTS.md — HoloViz MCP Server

A guide for AI coding agents contributing to this project.

---

## Project Overview

**Name**: HoloViz MCP Server
**Purpose**: MCP server that lets AI agents create interactive HoloViz visualizations rendered as live UIs inside LLM chat
**Language**: Python 3.11+
**Build system**: Pixi (conda-based) + Hatchling (PEP 517)
**Framework**: FastMCP 3.0+ (server composition via `mount()`)
**Key deps**: Panel, HoloViews, hvPlot, Bokeh, Pydantic, psutil, ruff

---

## Quick Start

```bash
curl -fsSL https://pixi.sh/install.sh | bash
cd Panel-mcp-live
pixi install
pixi run postinstall
hvmcp --help
```

---

## Architecture

Three layers:

1. **MCP Server** (`server/`) — FastMCP tools that AI agents call
2. **Display Server** (`display/`) — Panel subprocess that renders and serves visualizations
3. **MCP App Templates** (`templates/`) — HTML files that render as iframes in LLM chat

### Module Structure

```
src/holoviz_mcp_server/
├── cli.py               # Typer CLI: hvmcp serve / mcp / status
├── config.py            # Pydantic config + env var loading
├── validation.py        # 5-layer validation pipeline (ast, ruff, packages, extensions, runtime)
├── utils.py             # execute_in_module, find_extensions, validate_extension_availability
│
├── server/              # MCP server layer
│   ├── main.py          # Main FastMCP server + core tools
│   ├── compose.py       # Mounts sub-servers with namespaces
│   ├── panel_mcp.py     # pn.* sub-server (list, get, params, search)
│   ├── hvplot_mcp.py    # hvplot.* sub-server (list, get)
│   └── holoviews_mcp.py # hv.* sub-server (list, get)
│
├── introspection/       # Pure Python discovery functions (no MCP dependency)
│   ├── panel.py         # Panel component discovery (list_components, get_component, search_components)
│   ├── holoviews.py     # HoloViews element discovery (list_elements, get_element)
│   ├── hvplot.py        # hvPlot chart type discovery (list_plot_types, get_plot_type)
│   └── skills.py        # Skill file loading (list_skills, get_skill)
│
├── display/             # Panel subprocess system
│   ├── app.py           # Panel server entry point (run as subprocess via python app.py)
│   ├── manager.py       # PanelServerManager: start/stop/restart/health-check subprocess
│   ├── client.py        # DisplayClient: HTTP client (POST /api/snippet, GET /api/health)
│   ├── database.py      # SQLite + FTS5: stores all snippets permanently
│   ├── endpoints.py     # Tornado REST handlers for /api/snippet and /api/health
│   └── pages/           # Panel web UI pages
│       ├── view_page.py # Renders a single visualization by ID
│       ├── feed_page.py # Live feed of all visualizations
│       ├── add_page.py  # Manual snippet submission form
│       └── admin_page.py
│
├── templates/           # MCP App HTML (iframes rendered inline in LLM chat)
│   ├── show.html        # Chart viewer — BokehJS embed or iframe + click-to-insight
│   ├── stream.html      # Live streaming viewer with play/pause
│   ├── dashboard.html   # Dashboard with stats + filters
│   └── multi.html       # Multi-chart grid with linked selections
│
└── skills/              # Agent skill guides (SKILL.md with YAML frontmatter)
    ├── panel/SKILL.md
    ├── hvplot/SKILL.md
    ├── holoviews/SKILL.md
    ├── param/SKILL.md
    └── data/SKILL.md
```

### Server Composition

```python
main_mcp.mount(panel_mcp,     namespace="pn")      # pn.list, pn.get, pn.params, pn.search
main_mcp.mount(hvplot_mcp,    namespace="hvplot")  # hvplot.list, hvplot.get
main_mcp.mount(holoviews_mcp, namespace="hv")      # hv.list, hv.get
```

Core tools on main server: `show`, `stream`, `load_data`, `validate`, `handle_interaction`, `skill_list`, `skill_get`, `list_packages`.

### Data Flow

```
LLM calls show(code)
  → 5-layer validation (syntax → security → packages → extensions → runtime)
  → DisplayClient POSTs to Panel subprocess /api/snippet
  → Panel executes code, stores in SQLite
  → Returns URL or Bokeh JSON spec
  → MCP App HTML renders chart (BokehJS embed or iframe)
  → User clicks chart → postMessage("bokeh-tap")
  → HTML calls app.callServerTool("handle_interaction", ...)
  → Server returns insight → displayed in iframe
```

### Two Rendering Paths in show()

| Condition | Path | How |
|-----------|------|-----|
| `method="jupyter"` + pure HoloViews/hvPlot | Client-side BokehJS | Serialized to `json_item`, rendered by BokehJS in template |
| `method="panel"` or Panel widgets | Server-side iframe | Panel subprocess URL embedded in `<iframe>` |

### Validation Pipeline (validation.py)

1. **Syntax** — `ast.parse(code)` → `ast_check()`
2. **Security** — blocked imports (subprocess, socket, ctypes, pickle, etc.) + ruff security rules → `ruff_check()`
3. **Packages** — `importlib.util.find_spec()` for every import → `check_packages()`
4. **Extensions** — detect Panel extensions requiring `pn.extension()` → `validate_extension_availability()`
5. **Runtime** — execute in isolated `types.ModuleType` namespace → `validate_code()`

---

## Configuration

Environment variables (prefix `HOLOVIZ_MCP_SERVER_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5077 | Panel server port |
| `HOST` | 127.0.0.1 | Panel server host |
| `MAX_RESTARTS` | 3 | Max subprocess restart attempts |
| `DB_PATH` | `~/.holoviz-mcp-server/snippets/snippets.db` | SQLite path |
| `EXTERNAL_URL` | *(auto)* | Public URL override |
| `SKILLS_DIR` | *(builtin)* | Custom skills directory |

Auto-detects JupyterHub (`JUPYTERHUB_SERVICE_PREFIX`) and Codespaces (`CODESPACE_NAME`).

---

## CLI Commands

```bash
hvmcp serve        # Start Panel display server standalone
hvmcp mcp          # Start MCP server (stdio) — also auto-starts Panel subprocess
hvmcp status       # Check display server health
```

---

## Development Workflow

```bash
pixi run test            # pytest tests/ -v
pixi run test-coverage   # pytest with --cov
pixi run lint            # ruff check + format --check
pixi run format          # ruff format + check --fix
pixi run postinstall     # pip install -e . + fastmcp (run after structural changes)
```

---

## Code Style

- **Type hints**: Required on all new code (Python 3.11+ syntax: `X | Y`, `list[X]`)
- **Line length**: 120 characters
- **Imports**: Single-line, alphabetical (enforced by ruff isort)
- **Linter**: ruff (replaces black + isort + flake8)
- No docstrings, comments, or type annotations on code you didn't change

---

## Adding a New Tool

1. Choose the right sub-server (or `server/main.py` for core tools)
2. Add `@mcp.tool()` decorated async function
3. Add tests in `tests/`

## Adding a New Skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`)
2. Auto-discovered at runtime — no code changes needed

---

## Key Dependencies

| Package | Role |
|---------|------|
| `fastmcp>=3.0` | MCP server framework + tool/resource decorators |
| `panel` | Display server + web UI framework |
| `holoviews` | Declarative visualization layer |
| `hvplot` | High-level plotting API |
| `bokeh` | Rendering backend + JS interactivity |
| `pandas` | DataFrame support |
| `pydantic>=2.0` | Config models |
| `psutil` | Cross-platform process management |
| `requests` | HTTP client (MCP → Panel subprocess) |
| `typer` | CLI framework |
| `ruff` | Code validation + formatting |
