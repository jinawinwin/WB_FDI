# World Bank FDI Data Platform

A reproducible annual foreign direct investment (FDI) dataset and GitHub Pages dashboard with three top-level tabs: **Inward FDI**, **Outward FDI**, and **Inward–Outward / Bilateral Relationships**.

## First-stage scope

- Pull annual country-level observations from the World Bank World Development Indicators (WDI) API.
- Build long-panel and wide-panel CSV/JSON outputs from 1990 onward.
- Add global World Bank aggregates, country rankings by selected year, World Bank income groups, World Bank regions, geographic continents, and transparent analytical country clusters.
- Refresh data on the first day of each month, with manual refresh available in GitHub Actions.
- Keep the source series and the update timestamp with the data.

## Data definitions

| Field | WDI indicator | Interpretation |
|---|---|---|
| Inward FDI, current US$ | `BX.KLT.DINV.CD.WD` | Net FDI inflows into the reporting economy |
| Outward FDI, current US$ | `BM.KLT.DINV.CD.WD` | Net FDI outflows from the reporting economy |
| Inward FDI, % of GDP | `BX.KLT.DINV.WD.GD.ZS` | Net inflows divided by GDP |
| Outward FDI, % of GDP | `BM.KLT.DINV.WD.GD.ZS` | Net outflows divided by GDP |
| GDP, current US$ | `NY.GDP.MKTP.CD` | Economic size |
| Population | `SP.POP.TOTL` | Population |

These are **net flows**, not FDI stocks. Current-US-dollar amounts are nominal and are not inflation-adjusted. Negative values can occur and are retained.

## Bilateral relationship limitation

WDI country-level inflow/outflow series do not identify the immediate source or destination economy. The bilateral tab is therefore designed for **IMF Direct Investment Positions by Counterpart Economy (DIP, formerly CDIS)**. That source contains bilateral **positions/stocks**, not the same annual flow measure used in the first two tabs. The dashboard will not fabricate bilateral flows from aggregate data. See [IMF DIP](https://data.imf.org/en/Datasets/DIP); bilateral data should be added with source, reporting economy, counterpart economy, reference year, position direction, instrument and mirror-data flags.

## Outputs

The workflow creates:

- `data/fdi_country_panel.csv` and `data/fdi_country_panel.json`
- `data/fdi_global_panel.csv` and `data/fdi_global_panel.json`
- `data/fdi_group_panel.csv` and `data/fdi_group_panel.json`
- `data/data_status.json` (refresh time, sources and latest observation years)
- `data/bilateral_fdi_positions.csv` (schema template; no fabricated bilateral records)

Country panel rows are country-year observations. Group observations use each country's **current** World Bank income/region classification applied consistently across the historical series; they are not historical classification vintages. Strategic clusters are analyst-defined, overlap by design, and are not official World Bank classifications.

## Publish the dashboard

1. In the repository, open **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **main** and folder **/(root)**, then save.
4. After the first data workflow has completed, open the published Pages URL.

## Update data manually

Open **Actions → Refresh World Bank FDI data → Run workflow**. The workflow also runs automatically on the first day of each month (09:15 Korea Standard Time, subject to GitHub scheduling delays).

## Source and API

- [World Bank WDI API](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures)
- [WDI inward FDI metadata](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/BX.KLT.DINV.CD.WD)
- [WDI outward FDI metadata](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/BM.KLT.DINV.CD.WD)
- [IMF DIP dataset](https://data.imf.org/en/Datasets/DIP)

The World Bank Indicators API is public and does not require an API key.

https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
