"""Streamlit dashboard for bilateral real exchange rates using IMF SDMX 3.0."""
from io import StringIO
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

BASE = "https://api.imf.org/external/sdmx/3.0"
COUNTRIES = {
    "Australia": "AUS", "Brazil": "BRA", "Canada": "CAN", "China": "CHN",
    "Euro area": "G163", "France": "FRA", "Germany": "DEU",
    "India": "IND", "Indonesia": "IDN", "Italy": "ITA",
    "Japan": "JPN", "Mexico": "MEX", "South Africa": "ZAF",
    "South Korea": "KOR", "Switzerland": "CHE",
    "United Kingdom": "GBR", "United States": "USA",
}
HEADERS = {"Accept": "text/csv", "User-Agent": "real-exchange-rate-app/1.0 (public economic research)"}


class IMFDataError(Exception):
    """Readable data-download or validation error."""


def parse_csv(body: str, country: str, indicator: str) -> pd.Series:
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
        format="%Y-%m", errors="coerce"
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
            headers=HEADERS, timeout=(10, 40)
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise IMFDataError(f"IMF request failed for {country} {kind}: {exc}") from exc
    if not response.text.strip():
        raise IMFDataError(f"IMF returned no data for {country} {kind} ({key}).")
    return parse_csv(response.text, country, indicator)


def calculate_rer(a: str, b: str) -> pd.DataFrame:
    ca, cb = fetch_series(a, "cpi"), fetch_series(b, "cpi")
    ea = pd.Series(1.0, index=ca.index) if a == "USA" else fetch_series(a, "fx")
    eb = pd.Series(1.0, index=cb.index) if b == "USA" else fetch_series(b, "fx")
    data = pd.concat([
        ca.rename("CPI_A"), cb.rename("CPI_B"),
        ea.rename("FX_A"), eb.rename("FX_B")
    ], axis=1, join="inner").dropna()
    data = data.loc[(data > 0).all(axis=1)].copy()
    if data.empty:
        raise IMFDataError("No overlapping months with positive CPI and exchange-rate observations.")
    data["Nominal FX (A per B)"] = data["FX_A"] / data["FX_B"]
    data["RER level"] = data["Nominal FX (A per B)"] * data["CPI_B"] / data["CPI_A"]
    data["RER index"] = 100 * data["RER level"] / data["RER level"].iloc[0]
    data.index.name = "Month"
    return data


st.set_page_config(page_title="IMF Real Exchange Rate", page_icon="🌍", layout="wide")
st.title("Bilateral real exchange rate")
st.caption("IMF SDMX 3.0 · Monthly data since January 1976 where available · No API key")
names = list(COUNTRIES)
left, right = st.columns(2)
with left:
    a_name = st.selectbox("Country A (domestic)", names, index=names.index("United States"))
with right:
    b_name = st.selectbox("Country B (foreign)", names, index=names.index("Japan"))
a, b = COUNTRIES[a_name], COUNTRIES[b_name]
if a == b:
    st.warning("Choose two different economies.")
    st.stop()
with st.spinner("Downloading IMF observations..."):
    try:
        data = calculate_rer(a, b)
    except IMFDataError as exc:
        st.error(str(exc))
        st.info("Try another country pair. Some IMF series may be unavailable or temporarily inaccessible.")
        st.stop()
    except Exception as exc:
        st.error(f"Unable to prepare the chart: {exc}")
        st.stop()
st.caption(f"Common coverage: {data.index.min():%b %Y} – {data.index.max():%b %Y} ({len(data):,} months)")
one, two, three = st.columns(3)
one.metric("Latest RER index", f"{data['RER index'].iloc[-1]:,.2f}")
two.metric("Latest nominal FX (A per B)", f"{data['Nominal FX (A per B)'].iloc[-1]:,.4f}")
three.metric("Change from base month", f"{data['RER index'].iloc[-1] - 100:+,.1f}%")
fig = px.line(data.reset_index(), x="Month", y="RER index",
              title=f"{a_name} vs {b_name} (first common month = 100)")
fig.add_hline(y=100, line_dash="dash", line_color="gray")
fig.update_layout(hovermode="x unified", yaxis_title="Real exchange rate index")
st.plotly_chart(fig, use_container_width=True)
st.markdown(
    "**Definition:** RER(A/B) = (FX_A / FX_B) × (CPI_B / CPI_A). "
    "FX is local currency units per USD. A rising index represents real depreciation "
    "of A against B. The first common observation is normalized to 100."
)
st.info("This is a relative-price index, not a purchasing-power-parity price level. Missing months are not interpolated.")
with st.expander("View and download monthly data"):
    st.dataframe(data, use_container_width=True)
    st.download_button("Download CSV", data.to_csv().encode("utf-8"),
                       file_name=f"rer_{a}_{b}.csv", mime="text/csv")
st.caption("Source: IMF SDMX 3.0 CPI and ER dataflows. Availability varies by economy.")
