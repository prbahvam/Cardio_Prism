"""CARDIO-PRISM — Streamlit demo for the Finale.  Run: streamlit run app.py"""
import io
from pathlib import Path
import pandas as pd, streamlit as st, altair as alt
from agent_v2 import ingest, addressability, score, decide, sensitivity

HERE = Path(__file__).parent          # resolve next to this script, not the cwd

def find_data():
    exact = HERE / "Data_Set_Ascend_Season_4_2026.xlsx"
    if exact.exists():
        return exact
    hits = [p for p in sorted(HERE.glob("*.xlsx")) if not p.name.startswith("~$")]
    return hits[0] if hits else None

INK, ACCENT, COOL = "#12263A", "#C8102E", "#2E86AB"
st.set_page_config(page_title="CARDIO-PRISM", layout="wide")
st.markdown(f"<style>.stApp{{background:#FBFCFD}}h1,h2,h3{{color:{INK};letter-spacing:-.02em}}"
            f".eyebrow{{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:#5A7184}}</style>",
            unsafe_allow_html=True)

@st.cache_data(show_spinner="Scoring clusters…")
def load_all(data_bytes, min_size):
    df, g = ingest(io.BytesIO(data_bytes), min_size)
    g["status"], g["reason"] = addressability(g)
    s = score(g)
    g["stability"] = sensitivity(g, s)
    return g, s

with st.sidebar:
    st.markdown('<p class="eyebrow">Agent configuration</p>', unsafe_allow_html=True)
    min_size = st.slider("Minimum cluster size (₹ cr)", 25, 400, 100, 25)
    st.markdown("**Pillar weights**")
    wa = st.slider("A · Market attractiveness", 0.0, 1.0, 0.25, 0.05)
    wb = st.slider("B · Future potential", 0.0, 1.0, 0.35, 0.05)
    wc = st.slider("C · Competitive headroom", 0.0, 1.0, 0.20, 0.05)
    wd = st.slider("D · Right to win", 0.0, 1.0, 0.20, 0.05)
    a_cut = st.slider("Attractiveness threshold", 30, 70, 50, 5)
    d_cut = st.slider("Right-to-win threshold", 30, 70, 50, 5)
    hide_closed = st.checkbox("Hide CLOSED clusters", True)

path = find_data()
if path is not None:
    raw = path.read_bytes()
    st.sidebar.caption(f"Data: {path.name}")
else:
    st.warning("Cardiac dataset not found next to app.py — upload it below.")
    up = st.file_uploader("Cardiac dataset (.xlsx)", type=["xlsx"])
    if up is None:
        st.stop()
    raw = up.getvalue()

g, s = load_all(raw, min_size)
g["attract"], g["composite"], g["verdict"] = decide(g, s, (wa, wb, wc, wd), a_cut, d_cut)
view = g.join(s).sort_values("composite", ascending=False)
if hide_closed:
    view = view[view.status != "CLOSED"]

st.markdown('<p class="eyebrow">Cipla · Ascend Season 4</p>', unsafe_allow_html=True)
st.title("CARDIO-PRISM")
mkt = ((g.mat26.sum() / g.mat24.sum()) ** 0.5 - 1) * 100
st.caption(f"{len(g)} clusters · ₹{g.mat26.sum():,.0f} cr · market {mkt:.1f}% CAGR")

c = st.columns(4)
c[0].metric("Clusters screened", len(g))
c[1].metric("Beating the market", int((g.val_cagr > mkt).sum()))
c[2].metric("Closed / capped", f"{int((g.status=='CLOSED').sum())} / {int((g.status=='CAPPED').sum())}")
c[3].metric("Cipla share", f"{g.cipla.sum()/g.mat26.sum()*100:.2f}%")

st.divider()
st.subheader("Attractiveness × right to win")
p = view.reset_index().rename(columns={"SUBGROUP": "cluster"})
chart = alt.Chart(p).mark_circle(opacity=.78, stroke="white", strokeWidth=1).encode(
    x=alt.X("attract:Q", title="Market attractiveness (A+B+C)", scale=alt.Scale(domain=[0, 100])),
    y=alt.Y("D_right_to_win:Q", title="Cipla right to win", scale=alt.Scale(domain=[0, 100])),
    size=alt.Size("mat26:Q", title="₹ cr", scale=alt.Scale(range=[60, 1600])),
    color=alt.Color("verdict:N", scale=alt.Scale(range=[ACCENT, COOL, "#8FA6B8", "#C9D2D9", "#6C7A89"])),
    tooltip=["cluster", "status", alt.Tooltip("mat26", format=",.0f"),
             alt.Tooltip("val_cagr", format=".1f"), alt.Tooltip("vol_cagr", format=".1f"),
             alt.Tooltip("cipla_sh", format=".2f"), alt.Tooltip("stability", format=".0f"), "verdict"],
).properties(height=460)
labels = alt.Chart(p.nlargest(6, "composite")).mark_text(align="left", dx=9, dy=-9, fontSize=10).encode(
    x="attract:Q", y="D_right_to_win:Q", text="cluster:N")
st.altair_chart(chart + labels, use_container_width=True)

st.subheader("Ranked opportunities")
show = view.head(15)[["mat26", "added", "val_cagr", "vol_cagr", "nlem_exposure", "hhi",
                      "firms", "cipla_sh", "status", "composite", "stability", "verdict"]]
show.columns = ["₹cr", "₹cr added", "Val CAGR%", "Vol CAGR%", "NLEM%", "HHI", "Players",
                "Cipla%", "Status", "Score", "Stability%", "Verdict"]
st.dataframe(show.round(1), use_container_width=True, height=520)

st.caption("Stage 1 addressability runs before scoring. Stability = % of 400 random weight "
           "draws in which the cluster stays top-5.")
