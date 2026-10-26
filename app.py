"""Bilateral real and nominal exchange rates from IMF SDMX 3.0 (Python 3.12)."""
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

BASE = "https://api.imf.org/external/sdmx/3.0"
COUNTRIES = {
    "Australia": ("AUS", "AUD"), "Brazil": ("BRA", "BRL"),
    "Canada": ("CAN", "CAD"), "China": ("CHN", "CNY"),
    "Euro area": ("G163", "EUR"), "France": ("FRA", "EUR"),
    "Germany": ("DEU", "EUR"), "India": ("IND", "INR"),
    "Indonesia": ("IDN", "IDR"), "Italy": ("ITA", "EUR"),
    "Japan": ("JPN", "JPY"), "Mexico": ("MEX", "MXN"),
    "South Africa": ("ZAF", "ZAR"), "South Korea": ("KOR", "KRW"),
    "Switzerland": ("CHE", "CHF"), "United Kingdom": ("GBR", "GBP"),
    "United States": ("USA", "USD"),
}
HEADERS = {
    "Accept": "text/csv",
    "User-Agent": "real-exchange-rate-app/1.0 (public economic research)",
}


class IMFDataError(Exception):
    """An IMF download or validation error suitable for display to users."""


def parse_csv(body: str, country: str, indicator: str) -> pd.Series:
    """Parse monthly IMF CSV observations, retaining valid positive values."""
    try:
        frame = pd.read_csv(StringIO(body), low_memory=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise IMFDataError("IMF returned an empty or unreadable CSV response.") from exc
    required = {"TIME_PERIOD", "OBS_VALUE"}
    if not required.issubset(frame.columns):
        raise IMFDataError(f"IMF CSV is missing columns: {required - set(frame.columns)}")
    for column, value in (("COUNTRY", country), ("INDICATOR", indicator), ("FREQUENCY", "M")):
        if column in frame.columns:
            frame = frame.loc[frame[column].astype(str) == value]
    if frame.empty:
        raise IMFDataError(f"No monthly {indicator} observations found for {country}.")
    dates = pd.to_datetime(
        frame["TIME_PERIOD"].astype(str).str.replace(r"-M(\d{2})$", r"-\1", regex=True),
        format="%Y-%m", errors="coerce",
    )
    values = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    result = pd.Series(values.to_numpy(), index=dates, name=indicator)
    result = result.loc[result.index.notna() & result.notna() & (result > 0)]
    result = result.loc[result.index >= pd.Timestamp("1976-01-01")]
    result = result[~result.index.duplicated(keep="last")].sort_index()
    if result.empty:
        raise IMFDataError(f"No valid positive {indicator} data for {country} since 1976.")
    return result


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_series(country: str, kind: str) -> pd.Series:
    """Fetch one IMF monthly series; preserve the existing cached request logic."""
    if kind == "cpi":
        flow, indicator, suffix = "CPI", "CPI", "_T.IX.M"
    elif kind == "fx":
        flow, indicator, suffix = "ER", "XDC_USD", "PA_RT.M"
    else:
        raise ValueError("kind must be cpi or fx")
    if country == "USA" and kind == "fx":
        return pd.Series(dtype=float, name="XDC_USD")
    key = f"{country}.{indicator}.{suffix}"
    url = f"{BASE}/data/dataflow/IMF.STA/{flow}/~/{key}"
    try:
        response = requests.get(
            url, params={"c[TIME_PERIOD]": "ge:1976-M01"},
            headers=HEADERS, timeout=(10, 40),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise IMFDataError(f"IMF request failed for {country} {kind}: {exc}") from exc
    if not response.text.strip():
        raise IMFDataError(f"IMF returned no data for {country} {kind} ({key}).")
    return parse_csv(response.text, country, indicator)


def prepare_data(country1: str, country2: str) -> pd.DataFrame:
    """Align CPI and exchange-rate data and compute unnormalized RER."""
    p1, p2 = fetch_series(country1, "cpi"), fetch_series(country2, "cpi")
    e1 = pd.Series(1.0, index=p1.index) if country1 == "USA" else fetch_series(country1, "fx")
    e2 = pd.Series(1.0, index=p2.index) if country2 == "USA" else fetch_series(country2, "fx")
    data = pd.concat(
        [e1.rename("E1"), e2.rename("E2"), p1.rename("P1"), p2.rename("P2")],
        axis=1, join="inner",
    ).dropna()
    data = data.loc[(data > 0).all(axis=1)].copy()
    if data.empty:
        raise IMFDataError("No overlapping months with valid CPI and exchange-rate observations.")
    data["S"] = data["E2"] / data["E1"]
    data["RER"] = data["S"] * data["P1"] / data["P2"]
    data.index.name = "date"
    return data


def select_sample(data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, float]:
    """Rebase RER to the arithmetic mean over the chosen valid months."""
    sample = data.loc[(data.index >= start) & (data.index <= end)].copy()
    if sample.empty:
        raise IMFDataError("No valid overlapping observations in the selected date range.")
    rer_star = float(sample["RER"].mean())
    if not pd.notna(rer_star) or rer_star <= 0:
        raise IMFDataError("The selected sample has no valid positive RER average.")
    sample["RER_star"] = rer_star
    sample["Real_Index"] = 100.0 * sample["RER"] / rer_star
    return sample, rer_star


def plot_sample(sample: pd.DataFrame, mode: str, unit_label: str) -> go.Figure:
    """Plot real, nominal, or both series with independent axes."""
    both = mode == "Both"
    fig = make_subplots(specs=[[{"secondary_y": True}]]) if both else go.Figure()
    if mode in ("Real", "Both"):
        trace = go.Scatter(x=sample.index, y=sample["Real_Index"], mode="lines",
                           name="Real Index", line={"color": "#2563eb"})
        if both:
            fig.add_trace(trace, secondary_y=False)
        else:
            fig.add_trace(trace)
        fig.add_hline(y=100, line_dash="dash", line_color="gray",
                      annotation_text="Sample average = 100")
    if mode in ("Nominal", "Both"):
        trace = go.Scatter(x=sample.index, y=sample["S"], mode="lines",
                           name=f"Nominal S ({unit_label})", line={"color": "#ea580c"})
        if both:
            fig.add_trace(trace, secondary_y=True)
        else:
            fig.add_trace(trace)
    if both:
        fig.update_yaxes(title_text="Real Index (sample mean = 100)", secondary_y=False)
        fig.update_yaxes(title_text=unit_label, secondary_y=True)
    elif mode == "Real":
        fig.update_yaxes(title_text="Real Index (sample mean = 100)")
    else:
        fig.update_yaxes(title_text=unit_label)
    fig.update_layout(xaxis_title="Month", hovermode="x unified",
                      legend={"orientation": "h", "y": 1.12, "x": 0},
                      margin={"t": 70, "r": 80 if both else 30})
    return fig


def main() -> None:
    st.set_page_config(page_title="IMF Real Exchange Rate", page_icon="🌍", layout="wide")
    st.title("Bilateral real exchange rate")
    st.caption("IMF SDMX 3.0 · Monthly observations since January 1976 where available")
    names = list(COUNTRIES)
    col1, col2 = st.columns(2)
    with col1:
        name1 = st.selectbox("Country 1", names, index=names.index("United States"))
    with col2:
        name2 = st.selectbox("Country 2", names, index=names.index("Japan"))
    if name1 == name2:
        st.warning("Choose two different economies.")
        st.stop()
    code1, currency1 = COUNTRIES[name1]
    code2, currency2 = COUNTRIES[name2]
    unit_label = f"{currency2} per {currency1}"
    with st.spinner("Downloading IMF observations..."):
        try:
            data = prepare_data(code1, code2)
        except IMFDataError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Unable to load IMF observations: {exc}")
            st.stop()

    months = pd.period_range(data.index.min(), data.index.max(), freq="M")
    choices = [period.strftime("%Y-%m") for period in months]
    st.caption(f"Common valid coverage: {choices[0]} through {choices[-1]}. "
               "Some months within this range may have missing observations.")
    start_col, end_col = st.columns(2)
    with start_col:
        start_text = st.selectbox("Start month", choices, index=0)
    with end_col:
        end_text = st.selectbox("End month", choices, index=len(choices) - 1)
    start = pd.Timestamp(start_text + "-01")
    end = pd.Timestamp(end_text + "-01")
    if start > end:
        st.error("Start month must not be later than end month.")
        st.stop()
    try:
        sample, rer_star = select_sample(data, start, end)
    except IMFDataError as exc:
        st.error(str(exc))
        st.stop()

    mode = st.radio("Display", ["Real", "Nominal", "Both"], index=2, horizontal=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("RER* (selected-sample average)", f"{rer_star:,.6f}")
    m2.metric("Valid months used", f"{len(sample):,}")
    m3.metric(f"Latest S ({unit_label})", f"{sample['S'].iloc[-1]:,.4f}")
    st.plotly_chart(plot_sample(sample, mode, unit_label), use_container_width=True)
    st.markdown(
        f"**Nominal exchange rate:** S(t) = E2(t) / E1(t), in **{unit_label}**.  "
        "**Real exchange rate:** RER(t) = S(t) × P1(t) / P2(t).  "
        "**Sample benchmark:** RER* = arithmetic mean of RER(t) across valid selected months.  "
        "**Real Index(t):** 100 × RER(t) / RER*."
    )
    st.caption("The real index averages 100 over the selected valid observations (up to floating-point precision). "
               "Missing months are excluded, not interpolated.")
    export = sample[["E1", "E2", "S", "P1", "P2", "RER", "RER_star", "Real_Index"]].copy()
    export.insert(0, "date", export.index.strftime("%Y-%m"))
    export = export.reset_index(drop=True)
    with st.expander("Selected-sample data", expanded=False):
        st.dataframe(export, use_container_width=True, hide_index=True)
    st.download_button(
        "Download selected sample (CSV)", export.to_csv(index=False).encode("utf-8"),
        file_name=f"rer_{code1}_{code2}_{start_text}_{end_text}.csv", mime="text/csv",
    )
    st.caption("Source: IMF SDMX 3.0 CPI and ER dataflows. CPI and FX coverage varies by economy.")


if __name__ == "__main__":
    main()