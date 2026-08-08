# CARDIO-PRISM

Opportunity-prioritisation agent for the Indian cardiac market.
Built for **Cipla Ascend Season 4** by **Team Phoenix** — Yash Bagrecha, Prabhav Maheshwari (IIM Mumbai).

## What it does

Ranks molecule-class clusters by their probability of outperforming the market over 3–5 years,
weighted by Cipla's ability to actually capture that growth.

The design choice that distinguishes it: **addressability is screened before attractiveness.**
A cluster that cannot be entered — a proprietary molecule with licences already allocated, or one
under an NLEM/NPPA price ceiling — is removed from the universe rather than ranked low. Ranking it
would imply some weighting could select it. None can.

## Pipeline

| Stage | What happens |
|---|---|
| 0 · Ingest | SKU rows → molecule-class clusters ≥ ₹100 cr, rolled up on **parent** company (not division) |
| 1 · Addressability gate | `CLOSED` licensed molecule · `CAPPED` NLEM/NPPA ceiling · `OPEN` contestable |
| 2 · Scoring | Four pillars, percentile-normalised 0–100: attractiveness, future potential, competitive headroom, right to win |
| 3 · Decide | Attractiveness × right-to-win 2×2 → double down / attack / harvest / avoid |
| 4 · Stress-test | 400 random weight draws → rank stability per cluster |

Growth is measured in **absolute rupees added**, not percentages, and scored on **volume**
rather than value — MAT vs MAT CP separates real demand from price and mix.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Place the Cardiac dataset (`.xlsx`) next to `app.py`, or upload it through the app.

## Data

The market dataset is licensed competition material and is **not included in this repository**.
The app reads any `.xlsx` placed alongside it, or accepts one via the in-app uploader.

## Files

| File | Purpose |
|---|---|
| `agent_v2.py` | Scoring engine — ingest, addressability, pillars, decision, sensitivity |
| `app.py` | Streamlit interface with live weight sliders |
| `requirements.txt` | Dependencies |

## External sources

NLEM 2022 / DPCO 2013 Schedule-I · NPPA retail price notifications · Cardiological Society of
India dyslipidaemia guidance · Lipid Association of India LDL-C consensus · molecule licensing
disclosures from company filings and press releases.
