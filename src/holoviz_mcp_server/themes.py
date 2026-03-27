"""Theme colors and CSS variables for visualization rendering."""

THEME_COLORS = {
    "dark": {
        "label": "#94a3b8",
        "tick": "#475569",
        "grid": "#334155",
        "grid_alpha": 0.5,
        "title": "#e0e0e0",
        "legend_text": "#94a3b8",
    },
    "light": {
        "label": "#374151",
        "tick": "#d1d5db",
        "grid": "#e5e7eb",
        "grid_alpha": 0.8,
        "title": "#111827",
        "legend_text": "#374151",
    },
}

CSS_THEME_VARS = """
    body.theme-dark {
      --bg-body: #0f172a;
      --text-primary: #e0e0e0; --text-secondary: #94a3b8; --text-muted: #64748b;
      --bg-card: rgba(30,41,59,0.6); --bg-surface: rgba(15,23,42,0.5);
      --border: #334155; --accent: #818cf8; --accent-bg: rgba(99,102,241,0.08);
      --error: #f87171; --success: #4ade80; --warning: #f59e0b;
      --btn-bg: #1e293b; --btn-border: #334155; --input-bg: #0f172a;
    }
    body.theme-light {
      --bg-body: #ffffff;
      --text-primary: #1f2937; --text-secondary: #6b7280; --text-muted: #9ca3af;
      --bg-card: rgba(255,255,255,0.9); --bg-surface: rgba(249,250,251,0.8);
      --border: #e5e7eb; --accent: #6366f1; --accent-bg: rgba(99,102,241,0.06);
      --error: #dc2626; --success: #16a34a; --warning: #d97706;
      --btn-bg: #f9fafb; --btn-border: #d1d5db; --input-bg: #ffffff;
    }
"""
