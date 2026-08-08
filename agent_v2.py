"""
CARDIO-PRISM  —  Cardiac Opportunity Prioritisation Agent
Cipla | Ascend Season 4

Pipeline
  Stage 0  Ingest      SKU rows -> molecule-class clusters, parent-company roll-up
  Stage 1  Addressable Can Cipla legally/commercially enter?   CLOSED | CAPPED | OPEN
  Stage 2  Score       Four pillars, percentile-normalised
  Stage 3  Decide      Attractiveness x Right-to-win -> verdict
  Stage 4  Stress      Weight sensitivity -> rank stability

Design note: Stage 1 runs BEFORE scoring. A cluster that cannot be entered is
not a low-ranked opportunity, it is not an opportunity. Ranking it below others
implies it could be chosen with different weights. It cannot.
"""

import numpy as np
import pandas as pd

M24, M25, M26 = "MAT FEB'24", "MAT FEB'25", "MAT FEB'26"
C24, C26 = "MAT CP FEB'24", "MAT CP FEB'26"
Q24, Q26 = "QTY MAT FEB'24", "QTY MAT FEB'26"
CLUSTER, PARENT, FIRM = "SUBGROUP", "GROUP", "COMPANY"   # COMPANY = parent, not CLUSTER
CIPLA = "CIPLA*"

PILLARS = ["A_attractiveness", "B_future", "C_headroom", "D_right_to_win"]

# NLEM 2022 cardiovascular molecules (price-capped under DPCO Schedule-I).
# Source: NLEM 2022 / DPCO 2013 Schedule-I, 29 CV drugs. Rosuvastatin, ezetimibe,
# fenofibrate, saroglitazar and nicorandil are NOT scheduled.
NLEM_MOLECULES = {
    "AMLODIPINE", "ENALAPRIL", "HYDROCHLOROTHIAZIDE", "LABETALOL", "RAMIPRIL",
    "TELMISARTAN", "CHLORTALIDONE", "CHLORTHALIDONE", "LOSARTAN", "BISOPROLOL",
    "CARVEDILOL", "OLMESARTAN", "NIFEDIPINE", "PRAZOSIN", "CILNIDIPINE",
    "CLONIDINE", "MOXONIDINE", "HYDRALAZINE", "NEBIVOLOL", "ATORVASTATIN",
    "METOPROLOL", "DILTIAZEM", "VERAPAMIL", "DIGOXIN", "AMIODARONE",
    "CLOPIDOGREL", "FUROSEMIDE", "PROPRANOLOL", "SPIRONOLACTONE", "ATENOLOL",
}

# Clusters with an NPPA-fixed retail price confirmed in the public record.
NPPA_FIXED = {"C02I0B CHLORTAL+CILNIDIP+TELMIS", "C10A0A ATORVA + ASPIRIN"}


def cagr(end, start, years=2):
    end, start = np.asarray(end, float), np.asarray(start, float)
    out = np.full(end.shape, np.nan)
    ok = (start > 0) & (end > 0)
    out[ok] = ((end[ok] / start[ok]) ** (1 / years) - 1) * 100
    return out


def pct(s, invert=False):
    r = s.rank(pct=True, na_option="bottom")
    return ((1 - r if invert else r) * 100).round(1)


# ---------------------------------------------------------------- Stage 0
def ingest(path, min_size=100.0):
    df = pd.read_excel(path, sheet_name="Cardiac", header=0)
    for c in [M24, M25, M26, C24, C26, Q24, Q26]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    g = df.groupby(CLUSTER).agg(
        mat24=(M24, "sum"), mat25=(M25, "sum"), mat26=(M26, "sum"),
        cp24=(C24, "sum"), cp26=(C26, "sum"),
        q24=(Q24, "sum"), q26=(Q26, "sum"),
        brands=("BRANDS", "nunique"), firms=(FIRM, "nunique"))
    g["parent"] = df.groupby(CLUSTER)[PARENT].agg(lambda s: s.mode().iat[0])
    g["segment"] = df.groupby(CLUSTER)["CARDIAC SUB SEGMENTS"].agg(lambda s: s.mode().iat[0])

    g["val_cagr"] = cagr(g.mat26, g.mat24)
    g["real_cagr"] = cagr(g.cp26, g.cp24)
    g["vol_cagr"] = cagr(g.q26, g.q24)
    g["price_eff"] = g.val_cagr - g.real_cagr
    g["accel"] = cagr(g.mat26, g.mat25, 1) - cagr(g.mat25, g.mat24, 1)
    g["accel"] = g.accel.clip(-20, 20)          # cap base-effect artifacts
    g["vol_backing"] = np.where(g.val_cagr > 0, (g.vol_cagr / g.val_cagr).clip(-1, 1.5), np.nan)
    g["added"] = g.mat26 - g.mat24

    sh = df.groupby([CLUSTER, FIRM])[M26].sum().reset_index()
    tot = sh.groupby(CLUSTER)[M26].transform("sum")
    sh["s"] = np.where(tot > 0, sh[M26] / tot, 0)
    g["hhi"] = (sh.assign(s2=sh.s ** 2).groupby(CLUSTER).s2.sum() * 10000).round(0)
    g["leader"] = (sh.groupby(CLUSTER).s.max() * 100).round(1)
    g["brands_per_100cr"] = (g.brands / g.mat26.clip(lower=1) * 100).round(1)

    cip = df[df[FIRM] == CIPLA]
    g["cipla"] = cip.groupby(CLUSTER)[M26].sum().reindex(g.index).fillna(0)
    g["cipla_sh"] = (g.cipla / g.mat26.clip(lower=1e-9) * 100).round(2)
    pt = df.groupby(PARENT)[M26].sum()
    ps = (cip.groupby(PARENT)[M26].sum().reindex(pt.index).fillna(0) / pt.clip(lower=1e-9) * 100)
    g["adj_sh"] = g.parent.map(ps).fillna(0).round(2)

    cip_mols = set()
    for m in cip["MOLECULE_DESC"].dropna().unique():
        cip_mols.update(x.strip().upper() for x in str(m).split("+"))
    mols = df.groupby(CLUSTER)["MOLECULE_DESC"].apply(
        lambda s: {x.strip().upper() for m in s.dropna().unique() for x in str(m).split("+")})
    g["mol_overlap"] = mols.reindex(g.index).apply(
        lambda ms: round(len(ms & cip_mols) / max(len(ms), 1) * 100, 1))

    # pricing regime: share of cluster molecules that are NLEM-scheduled
    def nlem_share(ms):
        if not isinstance(ms, set) or not ms:
            return 0.0
        hits = sum(any(n in m for n in NLEM_MOLECULES) for m in ms)
        return round(hits / len(ms) * 100, 1)
    g["nlem_exposure"] = mols.reindex(g.index).apply(nlem_share)
    g["is_plain"] = df.groupby(CLUSTER)["Plain/Combination"].agg(
        lambda x: x.mode().iat[0]).reindex(g.index).astype(str).str.upper().str.startswith("PLAIN")

    return df, g[g.mat26 >= min_size].copy()


# ---------------------------------------------------------------- Stage 1
def addressability(g):
    """CLOSED = cannot enter. CAPPED = can enter, value growth regulated. OPEN = contestable."""
    status = pd.Series("OPEN", index=g.index)
    reason = pd.Series("", index=g.index)

    closed = (g.firms <= 3) & (g.leader >= 60)
    status[closed] = "CLOSED"
    reason[closed] = "Proprietary/licensed molecule - entry requires in-licensing"

    # NLEM schedules MOLECULES. NLEM 2022 makes no FDC recommendations, so a
    # combination of scheduled molecules is itself non-scheduled - which is why
    # the market has migrated to FDCs. Only plain scheduled molecules are capped,
    # plus any cluster NPPA has priced directly under new-drug / Para 19 powers.
    capped = (~closed) & (((g.is_plain) & (g.nlem_exposure >= 50))
                          | (g.index.isin(NPPA_FIXED)))
    status[capped] = "CAPPED"
    reason[capped] = "NLEM/NPPA ceiling price - value growth regulated, volume only"

    # FDCs built entirely from scheduled molecules price freely today but are the
    # most likely targets of future NPPA action. Flag, do not exclude.
    risk = (status == "OPEN") & (~g.is_plain) & (g.nlem_exposure >= 90)
    reason[status == "OPEN"] = "Contestable"
    reason[risk] = "Contestable - elevated future price-control risk (all-NLEM FDC)"
    return status, reason


# ---------------------------------------------------------------- Stage 2
def score(g):
    s = pd.DataFrame(index=g.index)
    s["A_attractiveness"] = (0.6 * pct(g.mat26) + 0.4 * pct(g.added)).round(1)
    s["B_future"] = (0.30 * pct(g.real_cagr) + 0.30 * pct(g.vol_cagr)
                     + 0.15 * pct(g.accel) + 0.25 * pct(g.vol_backing)).round(1)
    s["C_headroom"] = (0.40 * pct(g.hhi, True) + 0.30 * pct(g.brands_per_100cr, True)
                       + 0.30 * pct(g.leader, True)).round(1)
    s["D_right_to_win"] = (0.40 * pct(g.cipla_sh) + 0.35 * pct(g.adj_sh)
                           + 0.25 * pct(g.mol_overlap)).round(1)
    return s


# ---------------------------------------------------------------- Stage 3
def decide(g, s, w=(0.25, 0.35, 0.20, 0.20), a_cut=50, d_cut=50):
    wa, wb, wc, wd = w
    attract = (wa * s.A_attractiveness + wb * s.B_future + wc * s.C_headroom) / (wa + wb + wc)
    comp = (wa * s.A_attractiveness + wb * s.B_future
            + wc * s.C_headroom + wd * s.D_right_to_win) / sum(w)
    v = pd.Series("Avoid", index=s.index)
    v[(attract >= a_cut) & (s.D_right_to_win >= d_cut)] = "Build on strength"
    v[(attract >= a_cut) & (s.D_right_to_win < d_cut)] = "Attack - capability gap"
    v[(attract < a_cut) & (s.D_right_to_win >= d_cut)] = "Harvest"
    v[g.status == "CLOSED"] = "Partner or skip"
    return attract.round(1), comp.round(1), v


# ---------------------------------------------------------------- Stage 4
def sensitivity(g, s, n=400, seed=7):
    """Randomise weights; report how often each cluster stays in the top 5."""
    rng = np.random.default_rng(seed)
    open_idx = g.index[g.status != "CLOSED"]
    hits = pd.Series(0, index=g.index, dtype=int)
    for _ in range(n):
        w = rng.dirichlet([2, 2, 2, 2])
        _, comp, _ = decide(g, s, tuple(w))
        for c in comp.loc[open_idx].nlargest(5).index:
            hits[c] += 1
    return (hits / n * 100).round(1)


def run(path, min_size=100.0):
    df, g = ingest(path, min_size)
    g["status"], g["reason"] = addressability(g)
    s = score(g)
    g["attract"], g["composite"], g["verdict"] = decide(g, s)
    g["stability"] = sensitivity(g, s)
    return df, g.join(s).sort_values("composite", ascending=False)


if __name__ == "__main__":
    df, out = run("/mnt/user-data/uploads/Data_Set_Ascend_Season_4_2026.xlsx")
    pd.set_option("display.width", 250)
    print(f"Universe {len(out)} clusters | market Rs {out.mat26.sum():,.0f} cr")
    print(out.status.value_counts().to_string(), "\n")
    cols = ["mat26", "added", "val_cagr", "vol_cagr", "nlem_exposure", "hhi",
            "firms", "cipla_sh", "status", "composite", "stability", "verdict"]
    print(out[cols].head(20).round(1).to_string())
