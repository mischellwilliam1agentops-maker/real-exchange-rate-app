# IMF Bilateral Real Exchange Rate App

A Streamlit dashboard calculating monthly bilateral real exchange rates using the IMF SDMX 3.0 API.

## Features

- Select two economies, including the euro area (`G163`).
- Download monthly CPI and exchange rates since January 1976 where available.
- Plot an interactive real exchange rate index rebased to 100.
- Download aligned monthly data as CSV.
- Cache downloads for 24 hours, handle missing data and request failures.
- Set the United States USD-per-USD rate to 1.

## Calculation

`RER(A/B) = (FX_A / FX_B) * (CPI_B / CPI_A)`

FX denotes local currency units per USD. A rising RER index indicates real depreciation of economy A relative to economy B. The first overlapping valid month is normalized to 100. The resulting series measures relative changes, not purchasing-power-parity price levels.

## IMF data

Base API: https://api.imf.org/external/sdmx/3.0

- Monthly CPI: `{ISO3}.CPI._T.IX.M` from the `IMF.STA/CPI` dataflow.
- Monthly exchange rate: `{ISO3}.XDC_USD.PA_RT.M` from the `IMF.STA/ER` dataflow.
- No API key is needed; HTTP requests use a timeout and User-Agent.

## Run locally with Python 3.12

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Open https://share.streamlit.io/.
2. Create an app using this GitHub repository, branch `main`.
3. Set the main file path to `app.py`.
4. Select Python 3.12 in advanced settings if available.
5. Deploy. No secrets are required.

## Limitations

Series availability varies by economy and month. Missing months are not interpolated; the chart uses only overlapping valid observations. IMF endpoint behavior and the live deployment have not been verified in this environment.
