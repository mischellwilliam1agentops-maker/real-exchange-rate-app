# IMF Bilateral Real Exchange Rate Dashboard

Streamlit app (Python 3.12) for calculating and plotting monthly nominal and real bilateral exchange rates from the IMF SDMX 3.0 API.

## Run locally

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

Put `app.py`, `requirements.txt`, and `README.md` in the **root** of your GitHub repository. Visit https://share.streamlit.io/, choose **Deploy a public app from GitHub**, select your repository and branch `main`, set the main file to `app.py`, and select Python 3.12 in advanced settings if available. No secrets or API key are needed.

## Exchange-rate direction and formulas

Country 1 is the base currency, and Country 2 is the quote currency. The nominal rate **S(t)** is **units of Country 2 currency per one unit of Country 1 currency**.

- `E1(t)`: Country 1 local currency units per USD, from IMF.
- `E2(t)`: Country 2 local currency units per USD, from IMF.
- `S(t) = E2(t) / E1(t)`.
- `P1(t)` and `P2(t)`: Country 1 and Country 2 CPI indices.
- `RER(t) = S(t) * P1(t) / P2(t)`.
- `RER_star = mean(RER(t))` over valid months within the **selected** start/end period.
- `Real_Index(t) = 100 * RER(t) / RER_star`.

The **Real Index averages 100** over the selected valid sample (up to floating-point precision), rather than being anchored to the first month. Re-selecting countries or dates recomputes the sample benchmark and chart.

For example, UK → US is USD per GBP (often around 1.3); US → Japan is JPY per USD (often around 150). These figures are illustrative, not live quotations. Currency units appear on the nominal chart axis, e.g. `JPY per USD`.

## App controls

Select **Country 1** and **Country 2**. Start and end month dropdowns span the first through last months with common valid CPI and FX data for the pair. Months without all four valid observations are excluded from calculations. The **Real**, **Nominal**, and **Both** display selector switches between a real-index chart, an actual-unit nominal-rate chart, and a single dual-y-axis Plotly chart (real index on the left, nominal rate on the right).

The CSV export includes only the selected valid months, with columns in exactly this order:

`date, E1, E2, S, P1, P2, RER, RER_star, Real_Index`

The `date` column is `YYYY-MM`. `RER_star` is repeated for every row of the selected sample.

## IMF data source

Base URL: https://api.imf.org/external/sdmx/3.0

- CPI series key: `{ISO3}.CPI._T.IX.M` (IMF.STA/CPI dataflow).
- Exchange-rate series key: `{ISO3}.XDC_USD.PA_RT.M` (IMF.STA/ER dataflow, monthly period-average local currency per USD).
- Requested start: January 1976, where available.
- Euro area country code: `G163` (currency EUR).
- United States USD/USD exchange rate is always treated as `1.0` on CPI-covered months.

Requests use `requests`, a User-Agent header, and connection/read timeouts. `st.cache_data` caches downloads for 24 hours. API failures, empty series, invalid values, and absent overlap display readable Streamlit errors rather than crashing. No missing observations are interpolated.

## Interpretation and limitations

A higher RER under this definition indicates a real appreciation of Country 1 relative to Country 2. The CPI indices may have different reference periods, so the raw RER level and RER_star are sensitive to those index conventions; the sample-normalized Real Index describes relative movements. Date dropdowns cover the **common valid coverage endpoints**, not necessarily uninterrupted data. IMF series and endpoints can change; live API and Community Cloud behavior should be tested after deployment.