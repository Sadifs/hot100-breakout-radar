# Hot 100 Breakout Radar

Which artists are breaking, and which songs could break next? An A&R-style research tool built on every weekly
Billboard Hot 100 chart from August 1958 to November 2026.

## What it does

Built so anyone can use it, with a 30-second guide for people new to the charts.

- **Breaking Now:** artists whose first Hot 100 song arrived in the last 26 weeks, plus this week's fastest-rising songs.
- **Could Break Next:** recent songs that debuted outside the top 10, with each one's trend and its chance of reaching the top 10.
- **Artist Lookup:** every Hot 100 song for any artist, split into lead and featured-guest credits.
- **Song History:** the week-by-week chart path of any song, with gaps shown when it leaves the chart.
- **Does It Work?:** how often past predictions came true, in plain language, with full statistics for data-minded readers.
- **How It Was Built:** data sources, cleaning rules, the model, and known limits.

## Key result

Of songs that debut outside the top 10, only a small share ever reach it. A logistic regression that uses only a
song's first 3 chart weeks and its lead artist's earlier chart record ranks them far better than debut position:

| Test (train years → test years) | Test songs | Reached top 10 | Model ROC-AUC | Debut-position ROC-AUC | Hit rate in top 50 picks (model vs. debut position) |
|---|---|---|---|---|---|
| 1990-2015 → 2016-2025 | 5,350 | 4.2% | **0.87** | 0.60 | **72%** vs. 12% |
| Streaming era: 2013-2020 → 2021-2025 | 2,834 | 2.8% | **0.92** | 0.61 | **54%** vs. 10% |

A song's height on the chart in week 3 and its most recent week-over-week climb carry the most signal.

## Data cleaning and identity resolution

**Artist credits.** Billboard credits mix acts ("Earth, Wind & Fire", "Tyler, The Creator", "Simon & Garfunkel")
with collaborations ("Future & Metro Boomin", "Drake Featuring Future & Molly Santana"). Text after "Featuring" or
"With" becomes featured credits. A lead credit is split on commas, "&", "X", or "And" only when at least half of the
pieces are artists who also chart on their own and every other piece looks like a full personal name; otherwise it
stays whole as one act.

**Songs that change credits.** When Billboard adds a featured artist or re-credits a song mid-run, the new credit
arrives with more than one week on the chart. These runs (33 of them) are merged back into the earlier song with the
same title and a shared artist, so they are not mistaken for new debuts. Only true new entries are used for modeling.

**Other checks.** Exact duplicate rows in the source are removed, weeks are counted by chart order rather than calendar
days, and an artist's track record counts only songs that debuted before the song being scored.

Result: 356,374 chart entries, 32,766 songs, 38,267 credits, and 8,873 artists; 4,604 songs credit two or more artists.

Known limits: one-word guest names stay attached to the credit ("Drake, Don Toliver & Yebba"; for scoring, the song
still uses Drake's track record), and duos whose members also chart solo are split ("Sonny & Cher"). Double-sided singles appear as Billboard printed
them, so a song can show up both alone and as part of a pairing ("Something" and "Come Together/Something").

## Project structure

```
pipeline.py                 load weekly charts into DuckDB, parse credits, merge credit changes, build tables
sql/songs.sql               song-level debut, first 3 weeks, peak, top-10 outcome
sql/artists.sql             artist-level career start, lead vs. featured counts, recent activity
sql/backtest_features.sql   model features with no look-ahead
sql/breaking_now.sql        artists whose first credit came in the last 26 weeks
sql/climbers.sql            fastest climbers on the latest chart
analysis.py                 time-split backtests, watchlist scores, breaking-now tables
app.py                      Streamlit app (.streamlit/config.toml sets the theme)
tests/test_pipeline.py      credit-parser cases and database checks (pytest)
```

## Run it

Built with Python 3.13.

```bash
pip install -r requirements.txt
python pipeline.py      # downloads the chart data (about 44 MB) and builds data/processed/hot100.duckdb
python analysis.py      # backtests, watchlist, breaking-now tables
streamlit run app.py
pip install -r requirements-dev.txt && pytest -q   # optional checks
```

The processed database and outputs are committed, so the app runs without rebuilding.

## Data source and limits

Chart data: [mhollingshead/billboard-hot-100](https://github.com/mhollingshead/billboard-hot-100). The Hot 100 lags
streaming, social, and Shazam signals, and chart rules have changed over time as streaming was added, so fewer
songs climb into the top 10 today than in earlier decades. A production A&R tool would combine this with platform data.

## Author

Sadaf Sarbazi, M.S. Business Analytics, Loyola Marymount University  •  [linkedin.com/in/sadaf-sarbazi](https://linkedin.com/in/sadaf-sarbazi)
