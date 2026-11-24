"""
styling.py - the DATAWISE design system (colours, CSS) and the DIT logo helpers.

LOGO HANDLING
  * The logo file is  assets/dit_logo.png  (the official file, never edited).
  * The path is built from THIS file's location, so it works on your PC,
    in VS Code and on Streamlit Community Cloud (no C:\\ paths anywhere).
  * The image is shown through an HTML <img> tag with only `width` set and
    `height:auto`, so the original aspect ratio is always kept.
  * It sits on a white rounded card so the dark-navy lettering stays readable
    on the dark sidebar. The logo itself is not recoloured or modified.
  * If the file is missing, the text "DefineInfoTech" is shown instead and the
    application keeps running.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = PROJECT_ROOT / "assets" / "dit_logo.png"
COMPANY_NAME = "DefineInfoTech"

# Colour tokens (also used by the charts)
BLUE = "#2563eb"
PURPLE = "#7c3aed"
INDIGO = "#4f46e5"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#dc2626"
SLATE = "#64748b"
INK = "#0f172a"
PALETTE = [BLUE, PURPLE, "#0ea5e9", "#14b8a6", AMBER, "#ec4899", SLATE]


# --------------------------------------------------------------------------
# Logo
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def logo_bytes() -> bytes | None:
    """Raw bytes of the logo, or None if the file is missing/unreadable."""
    try:
        data = LOGO_PATH.read_bytes()
        return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None
    except OSError:
        return None


@lru_cache(maxsize=1)
def _logo_b64() -> str | None:
    data = logo_bytes()
    return base64.b64encode(data).decode("ascii") if data else None


def logo_html(width_px: int | None = None, align: str = "left") -> str:
    """
    HTML for the logo card. width_px=None means "fill the available width"
    (used in the sidebar). The image height is always automatic.
    """
    width = f"{width_px}px" if width_px else "100%"
    margin = {"left": "0", "center": "0 auto", "right": "0 0 0 auto"}.get(align, "0")
    encoded = _logo_b64()
    if encoded:
        inner = f'<img src="data:image/png;base64,{encoded}" alt="DefineInfoTech logo">'
        cls = "dit-logo-card"
    else:
        inner = COMPANY_NAME
        cls = "dit-logo-card dit-logo-fallback"
    return f'<div class="{cls}" style="width:{width};max-width:100%;margin:{margin};">{inner}</div>'


def render_logo(width_px: int | None = None, align: str = "left") -> None:
    """Show the logo (or the text fallback) at this point of the page."""
    st.markdown(logo_html(width_px, align), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, button, input, textarea, select {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif;
}
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.015em; color: #0f172a; }
h1 { font-weight: 800; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { border-right: 1px solid #1e293b; }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
.dit-logo-card {
    background: #ffffff; border-radius: 14px; padding: 8px 12px;
    box-shadow: 0 1px 3px rgba(15,23,42,.18); box-sizing: border-box;
}
.dit-logo-card img { display: block; width: 100%; height: auto; }
.dit-logo-fallback { font-weight: 800; color: #0f172a; text-align: center; padding: 12px; letter-spacing: .3px; }
.dw-brand { display:flex; align-items:center; gap:10px; margin: 14px 2px 4px; }
.dw-brand-badge {
    width: 38px; height: 38px; border-radius: 11px; display:flex; align-items:center; justify-content:center;
    background: linear-gradient(135deg,#2563eb,#7c3aed); color:#fff; font-weight:800; font-size:18px;
}
.dw-brand-name { color:#fff; font-weight:800; font-size:1.25rem; letter-spacing:.8px; line-height:1.1; }
.dw-brand-sub { color:#94a3b8; font-size:.72rem; line-height:1.25; }
.dw-side-card {
    background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.10); border-radius: 12px;
    padding: 10px 12px; margin-top: 10px; color:#e2e8f0; font-size:.82rem;
}
.dw-side-card b { color:#fff; }
.dw-side-label { color:#94a3b8; font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; margin-bottom:2px; }
.dw-side-note { color:#94a3b8; font-size:.72rem; line-height:1.35; margin-top:10px; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { border-radius: 10px; padding: .35rem .6rem; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebar"] [aria-current="page"] { background: linear-gradient(90deg, rgba(79,70,229,.55), rgba(124,58,237,.35)); }

/* ---------- headers ---------- */
.dw-header { display:flex; align-items:center; justify-content:space-between; gap:18px; flex-wrap:wrap; margin-bottom: 4px; }
.dw-title { font-size: 1.9rem; font-weight: 800; color:#0f172a; margin:0; line-height:1.15; }
.dw-subtitle { color:#64748b; margin: 2px 0 0; font-size:.98rem; }
.dw-hero {
    background: linear-gradient(135deg,#0f172a 0%,#312e81 55%,#7c3aed 100%); border-radius: 20px;
    padding: 30px 34px; color:#fff; box-shadow: 0 10px 30px rgba(49,46,129,.25); margin-bottom: 18px;
}
.dw-hero h1 { color:#fff; margin: 14px 0 4px; font-size: 2.2rem; }
.dw-hero p { color:#e0e7ff; margin: 0; font-size: 1.05rem; max-width: 760px; }

/* ---------- cards ---------- */
.dw-card {
    background:#fff; border:1px solid #e5e7f0; border-radius:16px; padding:16px 18px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px rgba(15,23,42,.05); height:100%;
}
.dw-card-label { color:#64748b; font-size:.74rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; }
.dw-card-value { font-size:1.85rem; font-weight:800; color:#0f172a; line-height:1.2; margin-top:2px; }
.dw-card-help { color:#94a3b8; font-size:.78rem; margin-top:2px; }
.dw-card.good .dw-card-value { color:#15803d; } .dw-card.warn .dw-card-value { color:#b45309; }
.dw-card.bad .dw-card-value { color:#b91c1c; } .dw-card.accent .dw-card-value { color:#4f46e5; }
.dw-pill { display:inline-block; border-radius:999px; padding:3px 12px; font-size:.78rem; font-weight:700; }
.dw-pill.good { background:#dcfce7; color:#166534; } .dw-pill.warn { background:#fef3c7; color:#92400e; }
.dw-pill.bad { background:#fee2e2; color:#991b1b; } .dw-pill.info { background:#e0e7ff; color:#3730a3; }
.dw-pill.neutral { background:#f1f5f9; color:#475569; }
.dw-section { font-size:1.15rem; font-weight:700; color:#0f172a; margin: 22px 0 8px; }
.dw-muted { color:#64748b; font-size:.9rem; }
.dw-demo-tag { background:#fef3c7; color:#92400e; border-radius:8px; padding:2px 8px; font-size:.72rem; font-weight:700; }
.dw-step { display:flex; gap:12px; align-items:flex-start; margin: 8px 0; }
.dw-step-n { flex:0 0 28px; height:28px; border-radius:50%; background:#eef2ff; color:#4338ca; font-weight:700; display:flex; align-items:center; justify-content:center; font-size:.85rem; }
.dw-step-t { color:#334155; font-size:.95rem; padding-top:3px; }
.dw-bar { height:10px; border-radius:99px; background:#e2e8f0; overflow:hidden; }
.dw-bar > span { display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,#2563eb,#7c3aed); }

/* ---------- controls ---------- */
.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: linear-gradient(135deg,#4f46e5,#7c3aed); border: 0; color:#fff;
}
div[data-testid="stTabs"] button[role="tab"] { font-weight: 600; }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #e5e7f0; }
div[data-testid="stExpander"] { border-radius: 12px; border: 1px solid #e5e7f0; background:#fff; }
div[data-testid="stFileUploaderDropzone"] { border-radius: 14px; border: 2px dashed #a5b4fc; background:#f8f9ff; }

@media (max-width: 800px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    .dw-title { font-size: 1.5rem; } .dw-card-value { font-size: 1.45rem; } .dw-hero { padding: 22px 20px; }
}
</style>
"""


def apply_global_css() -> None:
    """Inject the DATAWISE stylesheet (call once per page run, from app.py)."""
    st.markdown(_CSS, unsafe_allow_html=True)
