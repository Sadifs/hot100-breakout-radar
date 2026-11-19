"""
Hot 100 Breakout Radar: Streamlit app.
Who is breaking, which songs might break next, and how artists move from featured to lead credits.

Run:  streamlit run app.py   (pipeline.py and analysis.py write the files it reads)
"""
import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'processed'
REPO = 'https://github.com/Sadifs/hot100-breakout-radar'

st.set_page_config(page_title='Hot 100 Breakout Radar', page_icon='📈', layout='wide')


@st.cache_resource
def conn():
    return duckdb.connect(str(DATA / 'hot100.duckdb'), read_only=True)


@st.cache_data
def q(sql, params=None):
    return conn().execute(sql, params or []).df()


@st.cache_data
def load_csv(name):
    path = DATA / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def fmt_rank(x):
    return 'off chart' if pd.isna(x) or x >= 101 else f'{int(x)}'


def fmt_gain(x):
    if pd.isna(x):
        return '–'
    x = int(x)
    return f'+{x}' if x > 0 else ('0' if x == 0 else f'{x}')


def fmt_date(x):
    d = pd.Timestamp(x)
    return f'{d:%b} {d.day}, {d.year}'


def position_axis(fig):
    # chart positions run 1 (top) to 100; show them top-down with readable ticks and room for points at #1
    fig.update_yaxes(range=[104, -3], tickvals=[1, 20, 40, 60, 80, 100])
    return fig


metrics = json.loads((DATA / 'backtest_metrics.json').read_text())
counts = q('''SELECT (SELECT COUNT(*) FROM chart_entries) AS entries, (SELECT COUNT(*) FROM songs) AS songs,
                     (SELECT COUNT(*) FROM artists) AS artists, (SELECT MIN(chart_date) FROM chart_entries) AS first,
                     (SELECT MAX(chart_date) FROM chart_entries) AS last''').iloc[0]

st.title('Hot 100 Breakout Radar')
st.caption(f"Every weekly Billboard Hot 100 chart from {fmt_date(counts['first'])} to {fmt_date(counts['last'])}  •  "
           f"{counts['entries']:,} chart entries  •  {counts['songs']:,} songs  •  {counts['artists']:,} artists  •  "
           f"[Code and methods]({REPO})")

tabs = st.tabs(['Breaking Now', 'Watchlist', 'Artist Lookup', 'Song Trajectory', 'Backtest', 'Methods'])

# ---------------------------------------------------------------- Breaking Now
with tabs[0]:
    st.subheader('New artists')
    st.write('Artists whose first Hot 100 credit came in the last 26 chart weeks, ordered by best peak.')
    br = load_csv('breaking_artists.csv')
    if br.empty:
        st.info('No new artists in the last 26 weeks.')
    else:
        role = br.apply(lambda r: 'lead and featured' if r['n_lead'] and r['n_featured']
                        else ('lead' if r['n_lead'] else 'featured'), axis=1)
        view = pd.DataFrame({
            'Artist': br['artist'], 'First charted': br['first_chart_date'].map(fmt_date), 'Credited as': role,
            'Chart songs': br['n_songs'].astype(int), 'Best peak': br['best_peak'].astype(int),
            'Position this week': br['best_rank_this_week'].map(fmt_rank),
            'Change this week': br['biggest_gain_this_week'].map(fmt_gain),
        })
        st.dataframe(view, hide_index=True, width='stretch', height=390)
        st.caption('"Change this week" is the best week-over-week move among the artist\'s songs on the latest chart.')

    st.subheader('Fastest climbers this week')
    st.write('Songs 8 weeks old or younger with the biggest week-over-week gains on the latest chart.')
    cl = load_csv('climbers_this_week.csv')
    if cl.empty:
        st.info('No qualifying climbers this week.')
    else:
        top = cl.head(10).copy()
        top['label'] = top['song'] + '  –  ' + top['artist_credit']
        fig = px.bar(top.iloc[::-1], x='spots_gained', y='label', orientation='h',
                     hover_data={'rank': True, 'last_week': True, 'weeks_on_chart': True, 'label': False},
                     labels={'spots_gained': 'Spots gained this week', 'label': '', 'rank': 'Position',
                             'last_week': 'Last week', 'weeks_on_chart': 'Weeks on chart'})
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

# ---------------------------------------------------------------- Watchlist
with tabs[1]:
    st.subheader('Which recent songs could reach the top 10?')
    live_rate = metrics['streaming_2013_2020_to_2021_2025']['test_positive_rate']
    st.write('Songs that debuted outside the top 10 in the last 9 chart weeks and have not reached it yet. Each song is '
             'scored from its first 3 chart weeks and the lead artist\'s earlier chart record, using a model fit on '
             f'2013-2025 debuts. For context, only about {live_rate:.0%} of songs like these reach the top 10.')
    wl = load_csv('watchlist_scores.csv')
    if wl.empty:
        st.info('No songs currently qualify.')
    else:
        view = pd.DataFrame({
            'Song': wl['song'], 'Credit': wl['artist_credit'], 'Debut': wl['debut_date'].map(fmt_date),
            'Week 1': wl['rank_w1'].map(fmt_rank), 'Week 2': wl['rank_w2'].map(fmt_rank), 'Week 3': wl['rank_w3'].map(fmt_rank),
            'This week': wl['rank_this_week'].map(fmt_rank), 'Artist\'s earlier chart songs': wl['prior_songs'].astype(int),
            'Chance of top 10': (wl['top10_probability'] * 100).round(1).astype(str) + '%',
        })
        st.dataframe(view, hide_index=True, width='stretch', height=430)
        st.caption('Scores rank songs well in backtests but are rough as probabilities. Treat them as a shortlist, '
                   'not a forecast.')

# ---------------------------------------------------------------- Artist Lookup
with tabs[2]:
    st.subheader('Artist credit history')
    st.write('Every Hot 100 song for an artist, split into lead and featured credits. A run of features followed by '
             'lead hits is a common breakout path.')
    artists = q('SELECT artist FROM artists WHERE n_songs >= 2 ORDER BY n_songs DESC, artist')['artist'].tolist()
    who = st.selectbox('Artist', artists, index=artists.index('Doja Cat') if 'Doja Cat' in artists else 0)
    a = q('SELECT * FROM artists WHERE artist = ?', [who]).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Chart songs', int(a['n_songs']))
    c2.metric('Lead / featured', f"{int(a['n_lead'])} / {int(a['n_featured'])}")
    c3.metric('Top 10 hits', int(a['n_top10']))
    c4.metric('First charted', pd.Timestamp(a['first_chart_date']).strftime('%b %Y'))
    hist = q('''SELECT s.song, s.artist_credit, c.role, s.debut_date, s.peak_rank, s.total_weeks
                FROM credits c JOIN songs s USING (song_id) WHERE c.artist = ? ORDER BY s.debut_date''', [who])
    fig = px.scatter(hist, x='debut_date', y='peak_rank', color='role',
                     color_discrete_map={'lead': '#1f77b4', 'featured': '#ff7f0e'},
                     hover_data={'song': True, 'artist_credit': True, 'total_weeks': True},
                     labels={'debut_date': 'Debut', 'peak_rank': 'Peak position', 'role': 'Credited as',
                             'song': 'Song', 'artist_credit': 'Credit', 'total_weeks': 'Weeks on chart'})
    position_axis(fig)
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.dataframe(pd.DataFrame({
        'Song': hist['song'], 'Credit': hist['artist_credit'], 'Credited as': hist['role'],
        'Debut': hist['debut_date'].map(fmt_date), 'Peak': hist['peak_rank'].astype(int),
        'Weeks on chart': hist['total_weeks'].astype(int)}), hide_index=True, width='stretch', height=390)

# ---------------------------------------------------------------- Song Trajectory
with tabs[3]:
    st.subheader('Song trajectory')
    term = st.text_input('Search a song title', 'Not Like Us')
    matches = q('''SELECT song_id, song || '  –  ' || artist_credit || '  (' || strftime(debut_date, '%Y') || ')' AS label
                   FROM songs WHERE song ILIKE ? ORDER BY debut_date DESC LIMIT 25''', [f'%{term.strip()}%'])
    if term.strip() and len(matches):
        pick = st.selectbox('Song', matches['label'])
        sid = int(matches.loc[matches['label'] == pick, 'song_id'].iloc[0])
        tr = q('SELECT chart_week, chart_date, rank FROM chart_entries WHERE song_id = ? ORDER BY chart_week', [sid])
        # fill missing weeks so the line breaks when a song leaves the chart instead of bridging the gap
        weeks = q('SELECT DISTINCT chart_week, chart_date FROM chart_entries WHERE chart_week BETWEEN ? AND ? ORDER BY 1',
                  [int(tr['chart_week'].min()), int(tr['chart_week'].max())])
        tr = weeks.merge(tr[['chart_week', 'rank']], on='chart_week', how='left')
        fig = px.line(tr, x='chart_date', y='rank', markers=True, labels={'chart_date': 'Chart week', 'rank': 'Position'})
        fig.update_traces(connectgaps=False)
        position_axis(fig)
        fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        on = tr['rank'].notna()
        st.caption(f"Peak: {int(tr['rank'].min())}  •  Weeks on chart: {int(on.sum())}  •  "
                   f"First week: {fmt_date(tr.loc[on, 'chart_date'].min())}  •  Last week: {fmt_date(tr.loc[on, 'chart_date'].max())}")
    elif term.strip():
        st.info('No matching songs.')

# ---------------------------------------------------------------- Backtest
with tabs[4]:
    st.subheader('Can the first 3 chart weeks predict a climb into the top 10?')
    st.write('Each test uses only true new entries that debuted outside the top 10, trains on earlier years, and '
             'tests on later years, so the model never sees the future.')
    rows = []
    for key, name in [('main_1990_2015_to_2016_2025', 'Train 1990-2015, test 2016-2025'),
                      ('streaming_2013_2020_to_2021_2025', 'Streaming era: train 2013-2020, test 2021-2025')]:
        m = metrics[key]
        for model_key, model_name in [('baseline_debut_rank', 'Debut position only'), ('model', 'Early-trajectory model')]:
            r = m[model_key]
            rows.append({'Test': name, 'Model': model_name, 'Test songs': f"{m['test_songs']:,}",
                         'Reached top 10': f"{m['test_positive_rate']:.1%}", 'ROC-AUC': f"{r['roc_auc']:.2f}",
                         'PR-AUC': f"{r['pr_auc']:.2f}", 'Hit rate in top 50 picks': f"{r['precision_top50']:.0%}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    st.caption('Hit rate in top 50 picks: of the 50 test songs the model ranked highest, the share that actually '
               'reached the top 10.')
    st.subheader('What drives the score')
    coef = pd.DataFrame(metrics['standardized_coefficients'].items(), columns=['feature', 'coefficient'])
    names = {'height_w3': 'Height on the chart in week 3', 'climb_w1_w3': 'Climb from week 1 to week 3',
             'climb_w2_w3': 'Climb from week 2 to week 3', 'prior_songs': 'Artist\'s earlier chart songs',
             'prior_top10': 'Artist\'s earlier top 10 hits', 'has_feature': 'Has a featured artist',
             'n_artists': 'Number of credited artists'}
    coef['feature'] = coef['feature'].map(names)
    fig = px.bar(coef.sort_values('coefficient'), x='coefficient', y='feature', orientation='h',
                 labels={'coefficient': 'Standardized logistic regression coefficient', 'feature': ''})
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.caption('Bars to the right raise the score. Features are standardized, so bar lengths are comparable. Earlier '
               'chart songs and earlier top 10 hits move together (prolific artists chart many album tracks that rarely '
               'climb, while proven hitmakers do), so those two should be read as a pair.')

# ---------------------------------------------------------------- Methods
with tabs[5]:
    st.markdown(f'''
#### Data
Weekly Billboard Hot 100 charts from the public [mhollingshead/billboard-hot-100](https://github.com/mhollingshead/billboard-hot-100)
dataset, loaded into DuckDB by `pipeline.py`. SQL models in `sql/` build the song, artist, and credit tables. Exact
duplicate rows in the source (the same song listed twice in one week) are removed, keeping the better position.

#### Artist credits
Billboard credits mix acts ("Earth, Wind & Fire", "Tyler, The Creator") with collaborations ("Future & Metro Boomin").
Text after "Featuring" or "With" becomes featured credits. A lead credit is split on commas, "&", "X", or "And" only
when at least half of the pieces are artists who also chart on their own and every other piece looks like a full
personal name. Otherwise it stays whole as one act.

#### Songs that change credits
When Billboard adds a featured artist or re-credits a song mid-run, the new credit arrives with more than one week
already on the chart. Those runs are merged back into the earlier song with the same title and at least one shared
artist, so they are not counted as new debuts.

#### Backtest
Features: height on the chart in week 3 (101 minus position; off the chart counts as 0), the climb from week 1 to
week 3, the climb from week 2 to week 3 (weeks counted by chart order), the lead artist's earlier chart songs and top
10 hits (counted only before the debut, using the most established lead artist on the song), whether there is a
featured artist, and the number of credited artists. Logistic regression with standardized features and time-based
splits. Only true new entries (first week on the chart) are used.

#### Known limits
- One-word guest names stay attached to the credit ("Drake, Don Toliver & Yebba"), and duos whose members also chart
  solo are split ("Sonny & Cher"). Breaking Now leaves out combined credits that include an established artist.
- Double-sided singles appear as Billboard printed them, so a song can show up both alone and as part of a pairing
  ("Something" and "Come Together/Something").
- Fewer songs climb into the top 10 in the streaming era (about 3% recently vs. about 15% before 2016), so older
  patterns are only a rough guide.
- The Hot 100 lags streaming, social, and Shazam signals, and chart rules have changed over time. A real A&R tool
  would combine this with platform data.

Source code: [{REPO.replace('https://', '')}]({REPO})
''')
