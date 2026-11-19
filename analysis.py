"""
Hot 100 Breakout Radar: backtest and "breaking now" outputs.

1) Backtest. The question an A&R team actually asks: of songs that debut OUTSIDE the top 10, which will climb
   into it? Features use only a song's first 3 chart weeks plus the lead artist's record BEFORE the debut
   (no look-ahead). Only true new entries are used (weeks_on_chart = 1 at debut). Main split: train on debuts
   1990-2015, test on 2016-2025. Robustness split inside the streaming era: train 2013-2020, test 2021-2025.
   Logistic regression vs. a debut-position-only baseline.

2) Watchlist. Songs that debuted outside the top 10 in the last 9 chart weeks, have completed 3 chart weeks,
   and have not reached the top 10 yet, scored by the same model refit on streaming-era debuts (2013-2025),
   so scores reflect today's chart, where only about 3% of these songs climb into the top 10.

3) Breaking now. Artists whose first Hot 100 credit came in the last 26 chart weeks, plus this week's fastest
   climbers among songs 8 weeks old or younger.

Run:  python analysis.py   (after pipeline.py)
"""
import json
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'processed'
SQL = ROOT / 'sql'
# three non-overlapping views of the first 3 weeks (position, total climb, recent climb) plus track record and credits
FEATURES = ['height_w3', 'climb_w1_w3', 'climb_w2_w3', 'prior_songs', 'prior_top10', 'has_feature', 'n_artists']
SEP = re.compile(r', | & | X | x | And ')


def precision_at(scores, y, k=50):
    idx = np.argsort(-np.asarray(scores), kind='stable')[:k]
    return float(np.asarray(y)[idx].mean())


def main():
    con = duckdb.connect(str(OUT / 'hot100.duckdb'), read_only=True)
    for f in ['backtest_metrics.json', 'watchlist_scores.csv', 'breaking_artists.csv', 'climbers_this_week.csv']:
        (OUT / f).unlink(missing_ok=True)          # never leave a stale output behind

    songs = con.execute((SQL / 'backtest_features.sql').read_text()).df()
    songs['debut_year'] = pd.to_datetime(songs['debut_date']).dt.year
    latest_week = con.execute('SELECT MAX(chart_week) FROM chart_entries').fetchone()[0]
    latest_date = con.execute('SELECT MAX(chart_date) FROM chart_entries').fetchone()[0]

    pool = songs[(songs['is_new_entry'] == 1) & (songs['rank_w1'] > 10) & songs['debut_year'].between(1990, 2025)]

    def evaluate(train, test):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        model.fit(train[FEATURES], train['reached_top10'])
        y = test['reached_top10']
        p_model = model.predict_proba(test[FEATURES])[:, 1]
        p_base = -test['rank_w1'].to_numpy()          # baseline: a better debut position scores higher
        result = {
            'train_songs': int(len(train)), 'test_songs': int(len(test)),
            'train_positive_rate': round(float(train['reached_top10'].mean()), 4),
            'test_positive_rate': round(float(y.mean()), 4),
            'mean_predicted': round(float(p_model.mean()), 4),
            'model': {'roc_auc': round(roc_auc_score(y, p_model), 3), 'pr_auc': round(average_precision_score(y, p_model), 3),
                      'precision_top50': round(precision_at(p_model, y), 3)},
            'baseline_debut_rank': {'roc_auc': round(roc_auc_score(y, p_base), 3),
                                    'pr_auc': round(average_precision_score(y, p_base), 3),
                                    'precision_top50': round(precision_at(p_base, y), 3)},
        }
        return model, result

    yr = pool['debut_year']
    main_model, main_result = evaluate(pool[yr <= 2015], pool[yr >= 2016])
    _, streaming_result = evaluate(pool[yr.between(2013, 2020)], pool[yr >= 2021])
    coefs = dict(zip(FEATURES, main_model.named_steps['logisticregression'].coef_[0].round(3)))
    metrics = {
        'latest_chart': str(pd.Timestamp(latest_date).date()),
        'main_1990_2015_to_2016_2025': main_result,
        'streaming_2013_2020_to_2021_2025': streaming_result,
        'standardized_coefficients': {k: float(v) for k, v in coefs.items()},
    }
    (OUT / 'backtest_metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    recent = songs[(songs['is_new_entry'] == 1) & (songs['debut_week'] >= latest_week - 8)
                   & (songs['debut_week'] <= latest_week - 2) & (songs['rank_w1'] > 10) & (songs['reached_top10'] == 0)].copy()
    live = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    live_train = pool[yr.between(2013, 2025)]
    live.fit(live_train[FEATURES], live_train['reached_top10'])
    recent['top10_probability'] = live.predict_proba(recent[FEATURES])[:, 1].round(3) if len(recent) else []
    now = con.execute('SELECT song_id, rank AS rank_this_week FROM chart_entries WHERE chart_week = ?', [latest_week]).df()
    recent = recent.merge(now, on='song_id', how='left')
    recent.sort_values('top10_probability', ascending=False)[
        ['song', 'artist_credit', 'debut_date', 'rank_w1', 'rank_w2', 'rank_w3', 'rank_this_week', 'prior_songs',
         'top10_probability']
    ].to_csv(OUT / 'watchlist_scores.csv', index=False)

    breaking = con.execute((SQL / 'breaking_now.sql').read_text()).df()
    # drop combined credits the parser kept whole that still contain an established artist ("Drake & Qendresa")
    solo = set(con.execute('SELECT artist FROM artists').df()['artist'])
    established = {a for a in solo if not SEP.search(a)}
    breaking = breaking[~breaking['artist'].map(lambda a: bool(SEP.search(a)) and any(p in established for p in SEP.split(a)))]
    breaking.to_csv(OUT / 'breaking_artists.csv', index=False)
    con.execute((SQL / 'climbers.sql').read_text()).df().to_csv(OUT / 'climbers_this_week.csv', index=False)
    print('latest chart week:', latest_date, '| watchlist songs:', len(recent), '| new artists:', len(breaking))
    con.close()


if __name__ == '__main__':
    main()
