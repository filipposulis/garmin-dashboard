"""Glass look: CSS for Streamlit and a dark template for the Plotly charts."""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

PALETTE = ["#7DD3FC", "#A78BFA", "#5EEAD4", "#F9A8D4", "#FCD34D", "#FCA5A5"]
TEXT = "#C9D4F5"
MUTED = "#8C9AC4"
FONT = "Manrope, sans-serif"

_GLASS = """
    background: linear-gradient(135deg, rgba(255,255,255,0.07), rgba(255,255,255,0.025));
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 18px;
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    box-shadow: 0 10px 40px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.08);
"""

CSS = f"""
<style>
/* blue night background with blurred lights: gives the glass something to "see through" */
.stApp {{
    background:
        radial-gradient(900px 600px at 10% -10%, rgba(56,114,255,0.28), transparent 60%),
        radial-gradient(700px 500px at 95% 10%, rgba(167,139,250,0.22), transparent 60%),
        radial-gradient(800px 600px at 50% 110%, rgba(45,212,191,0.14), transparent 60%),
        linear-gradient(180deg, #060B1F 0%, #0A1433 100%);
    background-attachment: fixed;
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.5rem; max-width: 1400px; }}

/* sidebar */
[data-testid="stSidebar"] {{
    background: rgba(10,19,48,0.55);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.08);
}}

/* side menu */
[data-testid="stSidebarNav"] a {{
    border-radius: 12px; margin: 2px 0; transition: background .2s ease;
}}
[data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,0.06); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: rgba(125,211,252,0.14); border: 1px solid rgba(125,211,252,0.25);
}}
[data-testid="stNavSectionHeader"] {{
    text-transform: uppercase; letter-spacing: 0.14em; font-size: 0.68rem; color: #8C9AC4;
}}

/* title */
h1 {{ font-weight: 600 !important; letter-spacing: 0.01em; font-size: 3rem !important; }}
h2, h3 {{ font-weight: 600 !important; letter-spacing: 0.01em; }}

/* glass cards */
[data-testid="stMetric"] {{ {_GLASS} padding: 18px 20px; transition: transform .2s ease, border-color .2s ease; }}
[data-testid="stMetric"]:hover {{ transform: translateY(-2px); border-color: rgba(125,211,252,0.35); }}
[data-testid="stMetricLabel"] p {{
    text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.72rem !important; color: {MUTED};
}}
[data-testid="stPlotlyChart"] {{ {_GLASS} padding: 10px 12px; }}
[data-testid="stDataFrame"] {{ {_GLASS} padding: 6px; }}
[data-testid="stExpander"] details {{ {_GLASS} }}
[data-testid="stAlert"] > div {{ {_GLASS} }}

/* analysis cards (insights, alerts, records) */
.g-card {{ {_GLASS} padding: 16px 20px 16px 22px; margin-bottom: 14px; position: relative; overflow: hidden; }}
.g-card::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tone);
    box-shadow: 0 0 18px var(--tone);
}}
.g-card.g-good {{ --tone: #5EEAD4; }}
.g-card.g-bad {{ --tone: #FCA5A5; }}
.g-card.g-warn {{ --tone: #FCD34D; }}
.g-card.g-neutral {{ --tone: #7DD3FC; }}
.g-card ul {{ margin: 8px 0 0 0; padding-left: 18px; color: {TEXT}; font-size: .9rem; }}
.g-eyebrow {{ text-transform: uppercase; letter-spacing: .12em; font-size: .7rem; color: {MUTED}; margin-bottom: 4px; }}
.g-hero {{ font-family: 'Cormorant Garamond', serif; font-size: 2rem; font-weight: 600; line-height: 1.15;
           color: #F1F5FF; margin-bottom: 4px; }}
.g-big {{ font-size: 1.05rem; font-weight: 600; color: #F1F5FF; line-height: 1.4; margin-bottom: 6px; }}
.g-small {{ font-size: .86rem; color: {MUTED}; line-height: 1.5; }}
.g-pill {{
    display: inline-block; margin-top: 10px; padding: 2px 10px; border-radius: 999px; font-size: .72rem;
    letter-spacing: .06em; text-transform: uppercase; border: 1px solid var(--tone); color: var(--tone);
    background: rgba(255,255,255,0.03);
}}
.g-pill.g-good {{ --tone: #5EEAD4; }}
.g-pill.g-bad {{ --tone: #FCA5A5; }}
.g-pill.g-warn {{ --tone: #FCD34D; }}
.g-pill.g-neutral {{ --tone: #7DD3FC; }}

/* tabs as glass pills */
[data-testid="stTabs"] [role="tablist"] {{
    {_GLASS} padding: 6px; gap: 4px; border-radius: 999px; width: fit-content;
}}
[data-testid="stTabs"] [role="tab"] {{
    border-radius: 999px; padding: 6px 18px; height: auto; transition: background .2s ease;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background: rgba(125,211,252,0.15); }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}
</style>
"""


def _plotly_template() -> go.layout.Template:
    t = go.layout.Template()
    grid = "rgba(255,255,255,0.06)"
    t.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=TEXT, size=13),
        title=dict(font=dict(family=FONT, size=15, color="#E6ECFF"), x=0.01),
        colorway=PALETTE,
        xaxis=dict(gridcolor=grid, linecolor=grid, zeroline=False, title=None),
        yaxis=dict(gridcolor=grid, linecolor=grid, zeroline=False, title=None),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.12, x=1, xanchor="right"),
        hoverlabel=dict(bgcolor="#101A3C", bordercolor="rgba(255,255,255,0.15)", font=dict(family=FONT)),
        margin=dict(t=50, b=20, l=10, r=10),
        bargap=0.25,
    )
    t.data.bar = [go.Bar(marker=dict(line=dict(width=0), cornerradius=4))]
    t.data.scatter = [go.Scatter(line=dict(width=2.5, shape="spline"), marker=dict(size=6))]
    t.data.pie = [go.Pie(marker=dict(line=dict(color="#0A1433", width=2)))]
    return t


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    pio.templates["glass"] = _plotly_template()
    pio.templates.default = "glass"
