"""
SurakshaSetu Claims Console
Group 9, EY Applied Analytics & AI programme, Project 8

Run:  streamlit run app.py
Data: reads dbo.vw_ClaimMaster from SQL Server when SQL_CONN is set (see README),
      otherwise the CSV copies in ./data, which carry the same 900 claims.
"""
import os
import datetime as dt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------- settings
YEL, DARK, GREY, LIGHT, PALE = "#FFE600", "#2E2E38", "#747480", "#C4C4CD", "#F2F2F5"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)


def fpath(name):
    """Find a data file in ./data or next to app.py, whichever exists."""
    for cand in (os.path.join(DATA, name), os.path.join(HERE, name)):
        if os.path.exists(cand):
            return cand
    return os.path.join(DATA, name)
LOG = os.path.join(DATA, "approvals_log.csv")

st.set_page_config(page_title="SurakshaSetu Claims Console", page_icon="📋", layout="wide")
st.markdown(
    f"""
    <style>
      .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{background: #FFFFFF !important; color: {DARK} !important;}}
      [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{background: {PALE} !important; color: {DARK} !important;}}
      [data-testid="stSidebar"] * {{color: {DARK};}}
      [data-testid="stMultiSelectTagsContainer"] span span, [data-testid="stMultiSelectTagsContainer"] span span *,
      [data-baseweb="tag"], [data-baseweb="tag"] * {{color: #FFFFFF !important;}}
      [data-testid="stMultiSelectTagsContainer"] > span > span {{background: {DARK} !important;}}
      button[kind="primary"], button[kind="primary"] * {{background: {DARK} !important; color: #FFFFFF !important;}}
      .stApp p, .stApp li, .stApp label, .stApp span, .stMarkdown, [data-testid="stWidgetLabel"] p {{color: {DARK};}}
      [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{color: {DARK} !important;}}
      [data-testid="stTabs"] button p {{color: {DARK} !important;}}
      [data-testid="stDataFrame"], [data-testid="stTable"] {{background: #FFFFFF;}}
      .block-container {{padding-top: 1.2rem; padding-bottom: 2rem;}}
      h1, h2, h3 {{color: {DARK}; font-family: Arial, sans-serif;}}
      div[data-testid="stMetric"] {{background: {PALE}; border-left: 5px solid {YEL}; padding: 10px 14px; border-radius: 4px;}}
      div[data-testid="stMetricLabel"] p {{color: {DARK}; font-size: 0.9rem;}}
      div[data-testid="stMetricValue"] {{font-size: 1.7rem;}}
      .note {{background: {PALE}; border-left: 5px solid {DARK}; padding: 8px 12px; border-radius: 4px; color: {DARK};}}
      .sowhat, .sowhat * {{background: {DARK}; color: #FFFFFF !important; padding: 10px 14px; border-radius: 4px; font-weight: 600;}}
    </style>
    """,
    unsafe_allow_html=True,
)
px.defaults.template = "simple_white"
px.defaults.color_discrete_sequence = [DARK, YEL, GREY, LIGHT]
LAYOUT = dict(font=dict(family="Arial", color=DARK, size=13), margin=dict(l=10, r=10, t=50, b=10), title_font=dict(size=15))


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def load_claims():
    conn = os.environ.get("SQL_CONN")
    if not conn:
        try:
            conn = st.secrets["SQL_CONN"]
        except Exception:
            conn = None
    if conn:
        try:
            import pyodbc  # noqa: F401
            from sqlalchemy import create_engine
            eng = create_engine(f"mssql+pyodbc:///?odbc_connect={conn}")
            df = pd.read_sql("SELECT * FROM dbo.vw_ClaimMaster", eng)
            return df, "SQL Server (dbo.vw_ClaimMaster)"
        except Exception as e:  # fall back quietly, but say so
            st.session_state["sql_error"] = str(e)[:200]
    df = pd.read_csv(fpath("claims.csv"))
    return df, "local copy of the SQL view (data/claims.csv)"


@st.cache_data(show_spinner=False)
def load_aux():
    hr = pd.read_csv(fpath("human_reviews.csv"))
    wf = pd.read_csv(fpath("workflow_tests.csv"))
    return hr, wf


def load_bench():
    return pd.read_csv(fpath("benchmarks.csv"))


def load_log():
    if os.path.exists(LOG):
        return pd.read_csv(LOG)
    return pd.DataFrame(columns=["When", "Approver", "ClaimID", "Action", "Decision", "Note"])


def append_log(row):
    log = load_log()
    log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    log.to_csv(LOG, index=False)


def prepare(df, cutoff):
    d = df.copy()
    d["ReportedDate"] = pd.to_datetime(d["ReportedDate"])
    d["Month"] = d["ReportedDate"].dt.to_period("M").astype(str)
    d["Ref"] = (d["InvestigationReferral"] == "Yes").astype(int)
    d["Closed"] = (d["Status"] == "Closed").astype(int)
    d["HasMissing"] = d["HasMissing"].astype(int)
    d["CoverageUse"] = d["ClaimAmountINR"] / d["CoverageLimitINR"]
    q3 = d["ClaimAmountINR"].quantile(0.75)
    med_amt = d["ClaimAmountINR"].median()
    d["HighUse"] = (d["CoverageUse"] >= cutoff).astype(int)
    d["TopAmount"] = (d["ClaimAmountINR"] >= q3).astype(int)
    d["AboveMedian"] = (d["ClaimAmountINR"] > med_amt).astype(int)
    d["Score"] = 3 * d["HasMissing"] + 2 * d["HighUse"] + 1 * d["TopAmount"]
    d["Lane"] = np.where(d["HasMissing"] == 1, "A  Unblock", np.where(d["HighUse"] == 1, "B  Look closer", "C  Fast track"))
    d["Queue"] = np.select(
        [d["HasMissing"] == 1, d["HighUse"] == 1, d["AboveMedian"] == 1],
        ["Request documents", "Specialist review", "Standard"], "Fast-track")
    pct = (d["CoverageUse"] * 100).round(0).astype(int)
    d["Reason"] = np.select(
        [d["HasMissing"] == 1, d["HighUse"] == 1, d["AboveMedian"] == 1],
        ["Supporting evidence not on file; one document request to approve",
         "Claim uses " + pct.astype(str) + "% of the policy limit; reviewer picks Standard or Specialist",
         "Evidence on file, above-median amount; standard review"],
        "Evidence on file, below " + str(int(cutoff * 100)) + "% of limit, below-median amount; fast track, person approves payment")
    d["Band"] = pd.cut(d["CoverageUse"], [0, .3, .6, 10], labels=["< 30%", "30 to 60%", "60%+"], right=False)
    d["Over30"] = ((d["Closed"] == 1) & (d["ResolutionDays"] > 30)).astype(int)
    return d


def inr_cr(x):
    return f"Rs {x / 1e7:,.2f} cr"


def med(s):
    return float(np.median(s)) if len(s) else float("nan")


def bar(df, x, y, title, text=None, color=None, orientation="v", height=330, yfmt=None, colors=None):
    fig = px.bar(df, x=x, y=y, title=title, text=text if text else y, color=color, orientation=orientation, barmode="group",
                 color_discrete_sequence=colors or [DARK, YEL, GREY, LIGHT])
    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_color=DARK, marker_line_width=0.5)
    fig.update_layout(height=height, showlegend=color is not None, legend_title_text="", **LAYOUT)
    fig.update_xaxes(title="", tickangle=0)
    fig.update_yaxes(title="")
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    return fig


# ---------------------------------------------------------------- sidebar
raw, source = load_claims()
hr, wf = load_aux()

with st.sidebar:
    st.markdown(f"<h2 style='margin:0;color:{DARK}'>Suraksha<span style='background:{YEL};padding:0 4px'>Setu</span></h2>", unsafe_allow_html=True)
    st.caption("Claims Console  |  Group 9  |  Project 8")
    view = st.radio("View", ["Internal: operations", "External: published figures"], index=0)
    st.markdown("---")
    if view.startswith("Internal"):
        st.markdown("**Routing rule (live)**")
        cut_pct = st.slider("Gate 2: share of policy limit that sends a claim to Lane B", 40, 80, 60, 5, format="%d%%")
        cutoff = cut_pct / 100
        st.caption("Gate 1 is fixed: evidence on file or not. Changing Gate 2 re-sorts every lane, chart and queue on this screen.")
        approver = st.text_input("Signed in as (approver)", value="Claims manager")
        st.markdown("---")
    else:
        cutoff, approver = 0.60, ""
    st.markdown("**Filters**")
    df0 = prepare(raw, cutoff)
    regions = st.multiselect("Region", sorted(df0["Region"].unique()), default=sorted(df0["Region"].unique()))
    products = st.multiselect("Product", sorted(df0["ClaimType"].unique()), default=sorted(df0["ClaimType"].unique()))
    tiers = st.multiselect("Risk tier", ["Low", "Medium", "High"], default=["Low", "Medium", "High"])
    st.markdown("---")
    st.caption(f"Data: {source}. Claim amounts are reported amounts, not payouts. A referral is a review step, not a finding.")
    if "sql_error" in st.session_state:
        st.caption("SQL connection failed, using the local copy: " + st.session_state["sql_error"])

df = df0[df0["Region"].isin(regions) & df0["ClaimType"].isin(products) & df0["RiskTier"].isin(tiers)]
closed = df[df["Closed"] == 1]
openc = df[df["Closed"] == 0]
log = load_log()

# ================================================================ EXTERNAL VIEW
if view.startswith("External"):
    st.title("SurakshaSetu Insurance: claims service figures")
    st.markdown(f"<div class='note'>Figures published for policyholders and the regulator. Same source as the internal console; no claimant detail, no review queues, no scores.</div>", unsafe_allow_html=True)
    st.write("")
    c = st.columns(5)
    c[0].metric("Claims received (2025)", f"{len(df):,}")
    c[1].metric("Claims closed", f"{len(closed):,}", f"{len(closed) / max(len(df), 1):.0%} of received")
    c[2].metric("Median days to close", f"{med(closed['ResolutionDays']):.0f}")
    c[3].metric("Closed within 30 days", f"{1 - closed['Over30'].mean():.0%}")
    c[4].metric("Closed within 15 days", f"{(closed['ResolutionDays'] <= 15).mean():.0%}")
    st.write("")
    a, b = st.columns(2)
    byp = closed.groupby("ClaimType").agg(Claims=("ClaimID", "count"), Median_days=("ResolutionDays", "median"), Within_30=("Over30", lambda s: 1 - s.mean())).reset_index()
    a.plotly_chart(bar(byp, "ClaimType", "Median_days", "Median days to close, by product", height=340), use_container_width=True)
    byp["Within_30_pct"] = (byp["Within_30"] * 100).round(0)
    b.plotly_chart(bar(byp, "ClaimType", "Within_30_pct", "Share of claims closed within 30 days (%)", height=340), use_container_width=True)
    st.markdown("#### What to send with a claim")
    st.write("Three documents: the claim form, identity proof and the supporting evidence for the loss (bills, photos, reports). "
             "Claims that arrive with all three close in about 13 days; claims waiting for the evidence take about 33. "
             "If anything is missing we ask once, in one message, for everything at the same time.")
    st.markdown("#### Service commitments (IRDAI 2024 master circulars)")
    st.write("No claim is rejected for want of documents. A decision follows within 7 days of the surveyor's report. "
             "Health cashless requests are answered within 1 hour and discharge within 3. Late settlement carries interest at bank rate plus 2%.")
    st.caption("Ageing table in the format of the quarterly public disclosure:")
    age = pd.cut(closed["ResolutionDays"], [-1, 30, 90, 180, 10_000], labels=["Up to 30 days", "31 to 90 days", "91 to 180 days", "Over 180 days"])
    st.dataframe(closed.groupby([age, "ClaimType"], observed=True)["ClaimID"].count().unstack(fill_value=0), use_container_width=True)
    st.stop()

# ================================================================ INTERNAL VIEW
st.title("Claims Console: Monday review")
k = st.columns(7)
k[0].metric("Claims", f"{len(df):,}")
k[1].metric("Reported (Rs)", f"{df['ClaimAmountINR'].sum() / 1e7:,.2f} cr")
k[2].metric("Open", f"{len(openc)}", f"{int(openc['HasMissing'].sum())} no evidence", delta_color="inverse")
k[3].metric("Median days", f"{med(closed['ResolutionDays']):.0f}", "closed claims", delta_color="off")
k[4].metric("Missing evidence", f"{df['HasMissing'].mean():.1%}", f"{int(df['HasMissing'].sum())} claims", delta_color="off")
k[5].metric("Referred", f"{df['Ref'].mean():.1%}", f"{int(df['Ref'].sum())} claims", delta_color="off")
pending = openc[(openc["HasMissing"] == 1) & (~openc["ClaimID"].isin(log["ClaimID"]))]
k[6].metric("Awaiting approval", f"{len(pending)}", f"{len(log)} decided", delta_color="off")

tabs = st.tabs(["Overview", "Document gaps and time", "Review queue", "What-if: the cut-off", "Benchmark", "Controls and tests", "Data check"])

# ------------------------------------------------ Overview
with tabs[0]:
    a, b = st.columns(2)
    reg = df.groupby("Region").agg(Claims=("ClaimID", "count"), Amount_cr=("ClaimAmountINR", lambda s: s.sum() / 1e7)).reset_index()
    a.plotly_chart(bar(reg, "Region", "Claims", "Claims by region: volumes are even (205 to 242)"), use_container_width=True)
    prod = df.groupby("ClaimType").agg(Claims=("ClaimID", "count"), Amount_cr=("ClaimAmountINR", lambda s: round(s.sum() / 1e7, 2))).reset_index()
    prod["Share of claims %"] = (prod["Claims"] / prod["Claims"].sum() * 100).round(1)
    prod["Share of amount %"] = (prod["Amount_cr"] / prod["Amount_cr"].sum() * 100).round(1)
    long = prod.melt(id_vars="ClaimType", value_vars=["Share of claims %", "Share of amount %"], var_name="Measure", value_name="Share")
    b.plotly_chart(bar(long, "ClaimType", "Share", "Property is a third of claims and over half the money", color="Measure"), use_container_width=True)
    c, d = st.columns(2)
    mon = df.groupby("Month")["ClaimID"].count().reset_index(name="Claims")
    fig = px.line(mon, x="Month", y="Claims", title="Claims reported per month (59 to 92): no trend to forecast on", markers=True)
    fig.update_traces(line_color=DARK, marker_color=YEL, marker_size=9, marker_line_color=DARK, marker_line_width=1)
    fig.update_layout(height=330, **LAYOUT)
    c.plotly_chart(fig, use_container_width=True)
    grid = closed.pivot_table(index="ClaimType", columns="RiskTier", values="ResolutionDays", aggfunc="median").reindex(columns=["Low", "Medium", "High"])
    fig = px.imshow(grid, text_auto=True, color_continuous_scale=[[0, PALE], [1, YEL]], title="Median days to close by product and risk tier: 16 to 19 everywhere", aspect="auto")
    fig.update_layout(height=330, coloraxis_showscale=False, **LAYOUT)
    d.plotly_chart(fig, use_container_width=True)
    st.markdown("<div class='sowhat'>Risk tier explains none of the time. The next tab shows what does.</div>", unsafe_allow_html=True)

# ------------------------------------------------ Document gaps and time
with tabs[1]:
    a, b = st.columns(2)
    mr = df.groupby("Region")["HasMissing"].mean().mul(100).round(1).reset_index(name="Missing %")
    mp = df.groupby("ClaimType")["HasMissing"].mean().mul(100).round(1).reset_index(name="Missing %")
    a.plotly_chart(bar(mr, "Region", "Missing %", "Claims missing supporting evidence, by region (%)"), use_container_width=True)
    b.plotly_chart(bar(mp, "ClaimType", "Missing %", "Claims missing supporting evidence, by product (%)"), use_container_width=True)
    c, d = st.columns(2)
    t = closed.groupby(["ClaimType", "HasMissing"])["ResolutionDays"].median().reset_index()
    t["Evidence"] = t["HasMissing"].map({0: "On file", 1: "Missing"})
    allrow = closed.groupby("HasMissing")["ResolutionDays"].median().reset_index(); allrow["ClaimType"] = "All"; allrow["Evidence"] = allrow["HasMissing"].map({0: "On file", 1: "Missing"})
    t = pd.concat([allrow, t])
    c.plotly_chart(bar(t, "ClaimType", "ResolutionDays", "Median days to close: evidence on file vs missing (closed claims)", color="Evidence", colors=[LIGHT, DARK]), use_container_width=True)
    tail = closed[closed["Over30"] == 1]
    d.markdown("#### The long tail")
    d.metric("Closed claims that took over 30 days", f"{len(tail)}", f"{len(tail) / max(len(closed), 1):.0%} of closed")
    d.metric("Of those, missing evidence", f"{int(tail['HasMissing'].sum())}", f"{tail['HasMissing'].mean():.0%}" if len(tail) else "")
    d.metric("Open claims waiting on evidence", f"{int(openc['HasMissing'].sum())} of {len(openc)}", f"{openc['ResolutionDays'].min():.0f} to {openc['ResolutionDays'].max():.0f} days open" if len(openc) else "")
    d.metric("Claims closed with evidence never received", f"{int(((closed['HasMissing'] == 1)).sum())}", inr_cr(closed.loc[closed['HasMissing'] == 1, 'ClaimAmountINR'].sum()) + " reported; sent to audit", delta_color="off")
    st.markdown("<div class='sowhat'>Same gap in every region and product: the fix is the front door, not a region.</div>", unsafe_allow_html=True)

# ------------------------------------------------ Review queue
with tabs[2]:
    a, b = st.columns([1, 1])
    lane = df.groupby("Lane").agg(Claims=("ClaimID", "count"), Referral_rate=("Ref", "mean"), Median_days_closed=("ResolutionDays", lambda s: np.nan)).reset_index()
    lane["Median days (closed)"] = [med(closed.loc[closed["Lane"] == l, "ResolutionDays"]) for l in lane["Lane"]]
    lane["Referral rate %"] = (lane["Referral_rate"] * 100).round(1)
    lane["Share of claims %"] = (lane["Claims"] / lane["Claims"].sum() * 100).round(0)
    lane["Share of referrals %"] = (df.groupby("Lane")["Ref"].sum().values / max(df["Ref"].sum(), 1) * 100).round(0)
    a.plotly_chart(bar(lane.melt(id_vars="Lane", value_vars=["Share of claims %", "Share of referrals %"], var_name="Measure", value_name="Share"), "Lane", "Share",
                       f"Lanes at a {cutoff:.0%} cut-off: share of claims vs share of referrals", color="Measure", colors=[LIGHT, DARK]), use_container_width=True)
    b.markdown("#### Back-test on historical claims")
    b.dataframe(lane[["Lane", "Claims", "Median days (closed)", "Referral rate %"]].set_index("Lane"), use_container_width=True)
    ab = df[df["Lane"].str.startswith(("A", "B"))]
    b.markdown(f"<div class='note'>Lanes A and B hold <b>{len(ab) / len(df):.0%}</b> of claims and <b>{ab['Ref'].sum() / max(df['Ref'].sum(), 1):.0%}</b> of referrals, "
               f"using only what is known on the day a claim arrives.</div>", unsafe_allow_html=True)
    st.markdown("#### Today's list, highest score first")
    f1, f2, f3 = st.columns([1, 1, 2])
    lane_pick = f1.multiselect("Lane", sorted(df["Lane"].unique()), default=sorted(df["Lane"].unique()))
    status_pick = f2.multiselect("Status", ["Open", "Closed"], default=["Open"])
    q = df[df["Lane"].isin(lane_pick) & df["Status"].isin(status_pick)].sort_values(["Score", "ClaimAmountINR"], ascending=[False, False])
    show = q[["ClaimID", "ClaimType", "Region", "RiskTier", "ClaimAmountINR", "CoverageUse", "Status", "ResolutionDays", "Score", "Queue", "Reason"]].copy()
    show["CoverageUse"] = (show["CoverageUse"] * 100).round(0).astype(int).astype(str) + "%"
    show["ClaimAmountINR"] = show["ClaimAmountINR"].round(0).map("{:,.0f}".format)
    show = show.rename(columns={"ClaimAmountINR": "Amount (Rs)", "CoverageUse": "Of limit", "ResolutionDays": "Days", "RiskTier": "Tier", "ClaimType": "Product"})
    st.dataframe(show, use_container_width=True, hide_index=True, height=320)
    st.markdown("#### Approve a document request (Lane A, open claims)")
    st.caption("The console drafts one complete request. Nothing is sent until a named person approves it here; the decision is logged with time and approver.")
    cand = pending.sort_values("Score", ascending=False)
    if len(cand):
        c1, c2, c3 = st.columns([1.2, 2.5, 1])
        pick = c1.selectbox("Claim", cand["ClaimID"].tolist())
        r = cand[cand["ClaimID"] == pick].iloc[0]
        c2.markdown(f"<div class='note'><b>Draft request for {pick}</b><br>{r['ClaimType']} claim, {r['Region']}, reported {r['ReportedDate'].date()}, "
                    f"Rs {r['ClaimAmountINR']:,.0f} ({r['CoverageUse']:.0%} of limit), open {r['ResolutionDays']:.0f} days.<br>"
                    f"\"Dear claimant, to complete your claim {pick} we need the supporting evidence for the loss (bills, photos or reports). "
                    f"Please upload it in one go through the portal. Your claim form and identity proof are already on file.\"</div>", unsafe_allow_html=True)
        c3.write("")
        if c3.button("Approve and send", type="primary", use_container_width=True):
            append_log({"When": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "Approver": approver, "ClaimID": pick, "Action": "Document request", "Decision": "Approved", "Note": r["Reason"]})
            st.success(f"{pick}: request approved by {approver} and logged. The reminder flow (n8n) picks it up from here.")
            st.rerun()
        if c3.button("Reject draft", use_container_width=True):
            append_log({"When": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "Approver": approver, "ClaimID": pick, "Action": "Document request", "Decision": "Rejected", "Note": "Reviewer rejected the draft"})
            st.rerun()
    else:
        st.info("No open Lane A claims are waiting for approval in the current filter.")
    if len(log):
        st.markdown("##### Approval log")
        st.dataframe(log.sort_values("When", ascending=False), use_container_width=True, hide_index=True, height=200)

# ------------------------------------------------ What-if
with tabs[3]:
    rows = []
    for c in np.arange(0.40, 0.81, 0.05):
        flag = df["CoverageUse"] >= c
        rows.append({"Cut-off": f"{c:.0%}", "Share of claims in A + B %": round(flag.mean() * 100), "Share of referrals captured %": round(df.loc[flag, "Ref"].sum() / max(df["Ref"].sum(), 1) * 100), "c": round(c, 2)})
    wi = pd.DataFrame(rows)
    a, b = st.columns([1.3, 1])
    fig = go.Figure()
    fig.add_bar(x=wi["Cut-off"], y=wi["Share of claims in A + B %"], name="Share of claims flagged", marker_color=LIGHT, text=wi["Share of claims in A + B %"], textposition="outside")
    fig.add_bar(x=wi["Cut-off"], y=wi["Share of referrals captured %"], name="Share of referrals captured", text=wi["Share of referrals captured %"], textposition="outside",
                marker_color=[YEL if abs(c - cutoff) < 0.01 else DARK for c in wi["c"]], marker_line_color=DARK, marker_line_width=1)
    fig.update_layout(barmode="group", title=f"Gate 2 alone: claims flagged vs referrals caught by cut-off. Current setting {cutoff:.0%} highlighted", height=380, legend_title_text="", **LAYOUT)
    a.plotly_chart(fig, use_container_width=True)
    bands = df.groupby(pd.cut(df["CoverageUse"], np.arange(0, 1.01, 0.1), include_lowest=True), observed=True)["Ref"].agg(["count", "sum", "mean"]).reset_index()
    bands.columns = ["Band of limit used", "Claims", "Referred", "Rate"]
    bands["Rate %"] = (bands["Rate"] * 100).round(1)
    bands["Band of limit used"] = [f"{int(i.left * 100) if i.left > 0 else 0}-{int(i.right * 100)}" for i in bands["Band of limit used"]]
    fig = px.bar(bands, x="Band of limit used", y="Rate %", text="Rate %", title="Referral rate (%) by band of the limit used (%)")
    fig.update_traces(marker_color=[YEL if r > 15 else DARK for r in bands["Rate %"]], marker_line_color=DARK, textposition="outside", cliponaxis=False)
    fig.update_layout(height=380, **LAYOUT)
    fig.update_xaxes(title="", tickangle=0); fig.update_yaxes(title="")
    b.plotly_chart(fig, use_container_width=True)
    abf = df["Lane"].str.startswith(("A", "B"))
    st.markdown(f"<div class='sowhat'>Below 60% the bands run 3 to 8%; above, 18 to 23%. With the evidence gate added, Lanes A and B at {cutoff:.0%} hold "
                f"{abf.mean():.0%} of claims and {df.loc[abf, 'Ref'].sum() / max(df['Ref'].sum(), 1):.0%} of referrals. On real data this slider is re-tested every quarter.</div>", unsafe_allow_html=True)

# ------------------------------------------------ Benchmark
with tabs[4]:
    st.markdown(f"<div class='note'><b>Read with care.</b> SurakshaSetu figures come from one year of synthetic data. Public figures measure similar but not identical things, "
                f"and company numbers are self-reported. The page shows direction and the size of the gap, not a league table.</div>", unsafe_allow_html=True)
    st.write("")
    ours = {
        "Days to close with documents attached at intake": med(closed.loc[closed["HasMissing"] == 0, "ResolutionDays"]),
        "Days to close with paper or missing documents": med(closed.loc[closed["HasMissing"] == 1, "ResolutionDays"]),
        "On-time claim decisions after segmentation": round((1 - closed["Over30"].mean()) * 100),
        "Motor inspections processed straight through": round((1 - df["HasMissing"].mean()) * 100),
        "Claims settled instantly after queue segmentation": round((df["Lane"].str.startswith("C")).mean() * 100),
        "Health claims settled in the year": round(closed.shape[0] / max(len(df), 1) * 100),
        "Grey-zone claims needing a closer look": round(df["Ref"].mean() * 100, 1),
    }
    labels = {
        "Days to close with documents attached at intake": ("Evidence<br>on file", "days"),
        "Days to close with paper or missing documents": ("Evidence<br>missing", "days"),
        "On-time claim decisions after segmentation": ("Closed<br>within 30 days", "%"),
        "Motor inspections processed straight through": ("Complete<br>at intake", "%"),
        "Claims settled instantly after queue segmentation": ("Fast-lane<br>share", "%"),
        "Health claims settled in the year": ("Closed<br>in the year", "%"),
        "Grey-zone claims needing a closer look": ("Referral<br>rate", "%"),
    }
    bench = load_bench()
    comp = bench[bench["Measure"].isin(ours)].copy()
    comp["SurakshaSetu"] = comp["Measure"].map(ours)
    comp["Our measure"] = comp["Measure"].map(lambda m: labels[m][0])
    comp["Unit"] = comp["Measure"].map(lambda m: labels[m][1])
    a, b = st.columns(2)
    dcomp = comp[comp["Unit"] == "days"]
    fig = go.Figure()
    fig.add_bar(x=dcomp["Our measure"], y=dcomp["SurakshaSetu"], name="SurakshaSetu", marker_color=YEL, marker_line_color=DARK, text=dcomp["SurakshaSetu"], textposition="outside")
    fig.add_bar(x=dcomp["Our measure"], y=dcomp["Benchmark value"], name="Public benchmark (J.D. Power 2023)", marker_color=DARK, text=dcomp["Benchmark value"], textposition="outside")
    fig.update_layout(barmode="group", title="Days to close: the two-to-one gap is the industry's gap too", height=360, legend_title_text="", **LAYOUT)
    fig.update_xaxes(tickangle=0)
    a.plotly_chart(fig, use_container_width=True)
    pcomp = comp[comp["Unit"] == "%"]
    fig = go.Figure()
    fig.add_bar(x=pcomp["Our measure"], y=pcomp["SurakshaSetu"], name="SurakshaSetu", marker_color=YEL, marker_line_color=DARK, text=pcomp["SurakshaSetu"], textposition="outside")
    fig.add_bar(x=pcomp["Our measure"], y=pcomp["Benchmark value"], name="Public benchmark", marker_color=DARK, text=pcomp["Benchmark value"], textposition="outside",
                customdata=pcomp["Who"], hovertemplate="%{x}<br>%{y} (%{customdata})")
    fig.update_layout(barmode="group", title="Shares (%): where the market already is (hover for who)", height=360, legend_title_text="", **LAYOUT)
    fig.update_xaxes(tickangle=0)
    b.plotly_chart(fig, use_container_width=True)
    st.markdown("#### The full benchmark table (editable: add a row, correct a figure, it saves to data/benchmarks.csv)")
    theme = st.multiselect("Theme", sorted(bench["Theme"].unique()), default=sorted(bench["Theme"].unique()))
    edited = st.data_editor(bench[bench["Theme"].isin(theme)], use_container_width=True, hide_index=True, num_rows="dynamic", height=420, key="bench_editor")
    if st.button("Save benchmark table"):
        rest = bench[~bench["Theme"].isin(theme)]
        pd.concat([edited, rest]).to_csv(fpath("benchmarks.csv"), index=False)
        st.success("Saved.")
    st.markdown("<div class='sowhat'>Regulators now require collect, decide, explain; Indian insurers already run capped fast lanes. Our design is that pattern applied to this data.</div>", unsafe_allow_html=True)

# ------------------------------------------------ Controls and tests
with tabs[5]:
    a, b = st.columns(2)
    a.markdown("#### Human review control (Q1 finding, sent to audit)")
    hr2 = hr.copy()
    hr2["Changed"] = hr2["SuggestedQueue"] != hr2["ReviewerQueue"]
    hr2["HasReason"] = hr2["OverrideReason"].notna() & (hr2["OverrideReason"].astype(str).str.strip() != "")
    a.metric("Reviews on file", len(hr2))
    a.metric("Queue actually changed", int(hr2["Changed"].sum()), "all Specialist to Standard" if hr2["Changed"].sum() else "")
    a.metric("Override reason recorded", int(hr2["HasReason"].sum()), f"{int((hr2['HasReason'] & ~hr2['Changed']).sum())} with no change made", delta_color="inverse")
    a.dataframe(hr2[hr2["HasReason"]][["ReviewID", "ClaimID", "SuggestedQueue", "ReviewerQueue", "OverrideReason"]], use_container_width=True, hide_index=True, height=260)
    b.markdown("#### Workflow test cases (Q11 to Q13, test inbox only)")
    wf2 = wf.merge(df0[["ClaimID", "Status", "HasMissing", "ResolutionDays", "CoverageUse"]], on="ClaimID", how="left")
    wf2["Reminder should fire"] = np.where((wf2["Status"] == "Open") & (wf2["HasMissing"] == 1), "Yes", "No")
    b.dataframe(wf2[["TestID", "ClaimID", "Scenario", "ExpectedHumanAction", "Status", "HasMissing", "Reminder should fire"]], use_container_width=True, hide_index=True, height=420)
    b.caption("24 cases: the flow fired once (T009) and correctly held 23 times. A blind rule would have sent 7 wrong reminders and escalated 8 closed claims.")

# ------------------------------------------------ Data check
with tabs[6]:
    st.markdown("#### Control totals: every tool must show these")
    full = df0
    chk = pd.DataFrame([
        ["Claims", len(full), 900],
        ["Reported amount (Rs)", round(full["ClaimAmountINR"].sum(), 2), 243000973.88],
        ["Closed", int(full["Closed"].sum()), 863],
        ["Open", int((full["Closed"] == 0).sum()), 37],
        ["Referred", int(full["Ref"].sum()), 105],
        ["Missing supporting evidence", int(full["HasMissing"].sum()), 275],
        ["Median days, closed", med(full.loc[full["Closed"] == 1, "ResolutionDays"]), 17],
        ["Median days, closed and complete", med(full.loc[(full["Closed"] == 1) & (full["HasMissing"] == 0), "ResolutionDays"]), 13],
        ["Median days, closed and missing", med(full.loc[(full["Closed"] == 1) & (full["HasMissing"] == 1), "ResolutionDays"]), 33],
        ["Lane A / B / C at 60%", "see below", "275 / 252 / 373"],
    ], columns=["Measure", "This console", "Expected (Excel, SQL, notebook)"]).astype(str)
    st.dataframe(chk, use_container_width=True, hide_index=True)
    d60 = prepare(raw, 0.60)
    st.write("Lanes at 60%: " + " / ".join(f"{k}: {v}" for k, v in d60["Lane"].value_counts().sort_index().items()) +
             ".  Queues: " + " / ".join(f"{k}: {v}" for k, v in d60["Queue"].value_counts().items()) + ".")
    st.caption("Wrong join for reference: Claims joined straight to Documents gives 2,700 rows and Rs 72,90,02,921.64, three times the truth. The console never joins Documents; it reads the one-row-per-claim view.")
    st.markdown("#### Leakage check")
    st.write("The score uses HasMissing, CoverageUse and ClaimAmountINR only. Status, ResolutionDays and InvestigationReferral are outcomes; they appear in charts and back-tests but never in the score.")
