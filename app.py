"""
Hot 100 Breakout Radar: Streamlit app.
Who is breaking, which songs might break next, and how artists move from featured to lead credits.
Written so that someone with no music-industry or data background can use it.

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
LINKEDIN = 'https://linkedin.com/in/sadaf-sarbazi'

ACCENT = '#F2A541'      # amber: highlights, lead credits
BLUE = '#5B8DEF'        # featured credits, secondary series
GRID = 'rgba(255,255,255,0.08)'

st.set_page_config(page_title='Hot 100 Breakout Radar', page_icon='📈', layout='wide')
st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1200px;}
  [data-testid="stMetricValue"] {font-size: 1.8rem;}
  [data-testid="stMetricLabel"] p {color: #A9ADB5;}
  .hero {font-size: 2.9rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 0.2rem; padding-bottom: 0;
         color: #E8E6E3 !important;}
  .hero .accent {color: #F2A541 !important;}
  .hero a {display: none;}
  .tagline {font-size: 1.15rem; color: #C9CCD1; margin-top: 0.1rem; margin-bottom: 1.2rem;}
  [data-testid="stMetric"] {background: #161A22;}
  button[data-baseweb="tab"] p {font-size: 1.02rem; font-weight: 600;}
  [data-testid="stTabs"] {margin-top: 0.8rem;}
  h3 {border-left: 4px solid #F2A541; padding-left: 0.6rem !important;}
  .footer {color: #8A8F98; font-size: 0.85rem; margin-top: 2rem; padding-top: 1rem;
           border-top: 1px solid rgba(255,255,255,0.08);}
  .footer a {color: #C9CCD1;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data access
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


# ---------------------------------------------------------------- formatting
def fmt_rank(x):
    return 'off chart' if pd.isna(x) or x >= 101 else f'#{int(x)}'


def fmt_gain(x):
    if pd.isna(x):
        return '–'
    x = int(x)
    return f'up {x}' if x > 0 else ('no change' if x == 0 else f'down {-x}')


def fmt_date(x):
    d = pd.Timestamp(x)
    return f'{d:%b} {d.day}, {d.year}'


def style(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#E8E6E3', size=13),
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0, title=None),
                      hoverlabel=dict(bgcolor='#1A1E27'))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def position_axis(fig):
    # chart positions run #1 (top) to #100; show them top-down with readable ticks and room for points at #1
    fig.update_yaxes(range=[104, -3], tickvals=[1, 20, 40, 60, 80, 100], ticktext=['#1', '#20', '#40', '#60', '#80', '#100'])
    return fig


def show(fig):
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


# ---------------------------------------------------------------- shared inputs
metrics = json.loads((DATA / 'backtest_metrics.json').read_text())
main_bt = metrics['main_1990_2015_to_2016_2025']
stream_bt = metrics['streaming_2013_2020_to_2021_2025']
counts = q('''SELECT (SELECT COUNT(*) FROM chart_entries) AS entries, (SELECT COUNT(*) FROM songs) AS songs,
                     (SELECT COUNT(*) FROM artists) AS artists, (SELECT MIN(chart_date) FROM chart_entries) AS first,
                     (SELECT MAX(chart_date) FROM chart_entries) AS last''').iloc[0]
breaking = load_csv('breaking_artists.csv')
watch = load_csv('watchlist_scores.csv')
climbers = load_csv('climbers_this_week.csv')
model_hit = main_bt['model']['precision_top50']
base_hit = main_bt['baseline_debut_rank']['precision_top50']

# ---------------------------------------------------------------- header
st.markdown('<h1 class="hero">Hot 100 <span class="accent">Breakout Radar</span></h1>', unsafe_allow_html=True)
st.markdown('<p class="tagline">Spot the artists who are breaking out and the songs that could become hits next, '
            'using every Billboard Hot 100 chart since 1958.</p>', unsafe_allow_html=True)

with st.expander('New here? Start with this 30-second guide', expanded=True):
    g1, g2 = st.columns(2, gap='large')
    with g1:
        st.markdown('''
**What is the Billboard Hot 100?**
The weekly ranking of the 100 most popular songs in the U.S., based on streams, radio play, and sales.
**#1 is the top spot.** A song's first week on the chart is its **debut**.

**What does "breaking out" mean?**
A new artist or song quickly gaining popularity. Record labels' talent scouts (the **A&R** team, short for
"artists and repertoire") try to spot this early.
''')
    with g2:
        st.markdown('''
**How to use this app**
1. **Breaking Now:** artists who just appeared on the chart, and this week's fastest-rising songs.
2. **Could Break Next:** recent songs the model thinks might reach the top 10.
3. **Artist Lookup** and **Song History:** explore any artist or song since 1958.
4. **Does It Work?** How often the predictions came true in the past.

**Lead vs. featured:** the lead artist is the main name on a song; a featured artist is a guest ("featuring ...").
''')

k1, k2, k3, k4 = st.columns(4)
k1.metric('Latest chart week', fmt_date(counts['last']), border=True, height=128)
k2.metric('New artists in the last 6 months', f'{len(breaking):,}', border=True, height=128)
k3.metric('Songs that could break next', f'{len(watch):,}', border=True, height=128)
k4.metric('Past predictions that came true', f'{model_hit:.0%}',
          f'vs. {base_hit:.0%} by rule of thumb', delta_color='off', delta_arrow='off',
          border=True, height=128, help='Of the 50 songs the model rated highest in a 2016-2025 test, the share that actually reached the top 10.')

tabs = st.tabs(['🔥 Breaking Now', '🔮 Could Break Next', '🎤 Artist Lookup', '📈 Song History', '✅ Does It Work?',
               '🛠️ How It Was Built'])

# ---------------------------------------------------------------- Breaking Now
with tabs[0]:
    st.subheader('New artists on the chart')
    st.caption('Artists whose first-ever Hot 100 song arrived in the last 26 weeks, best performers first.')
    if breaking.empty:
        st.info('No new artists in the last 26 weeks.')
    else:
        role = breaking.apply(lambda r: 'lead and guest' if r['n_lead'] and r['n_featured']
                              else ('lead artist' if r['n_lead'] else 'featured guest'), axis=1)
        view = pd.DataFrame({
            'Artist': breaking['artist'], 'First appeared': breaking['first_chart_date'].map(fmt_date),
            'Role': role, 'Songs': breaking['n_songs'].astype(int),
            'Highest spot': breaking['best_peak'].astype(int).map(lambda v: f'#{v}'),
            'This week': breaking['best_rank_this_week'].map(fmt_rank),
            'Last 7 days': breaking['biggest_gain_this_week'].map(fmt_gain),
        })
        st.dataframe(view, hide_index=True, width='stretch', height=390)
        st.caption('"This week" is the artist\'s best spot on the newest chart; "Last 7 days" is how many spots that '
                   'song moved since the week before.')

    st.subheader('Fastest-rising songs this week')
    st.caption('Songs 8 weeks old or younger that jumped the most spots since last week.')
    if climbers.empty:
        st.info('No qualifying songs this week.')
    else:
        top = climbers.head(10).copy()
        credit = top['artist_credit'].map(lambda c: c if len(c) <= 40 else c[:38].rstrip(' ,&') + '…')
        top['label'] = top['song'] + '  –  ' + credit
        top['text'] = 'up ' + top['spots_gained'].astype(int).astype(str) + ', now #' + top['rank'].astype(int).astype(str)
        fig = px.bar(top.iloc[::-1], x='spots_gained', y='label', orientation='h', text='text',
                     color_discrete_sequence=[ACCENT],
                     hover_data={'artist_credit': True, 'rank': True, 'last_week': True, 'label': False, 'text': False},
                     labels={'spots_gained': 'Spots gained this week', 'label': '', 'rank': 'Now',
                             'last_week': 'Last week', 'artist_credit': 'Artist'})
        fig.update_traces(textposition='outside', cliponaxis=False)
        fig.update_xaxes(range=[0, top['spots_gained'].max() * 1.35], showticklabels=False, showgrid=False, title=None)
        show(style(fig, height=430))

# ---------------------------------------------------------------- Could Break Next
with tabs[1]:
    st.subheader('Songs that could break into the top 10 next')
    st.write('These songs debuted outside the top 10 in the last couple of months and have not made it there yet. Each '
             'gets a score based on how it moved in its first 3 weeks and how many hits its artist already has. '
             f"Normally only about **{stream_bt['test_positive_rate']:.0%}** of songs like these ever reach the top 10, "
             'so a score well above that is worth watching.')
    if watch.empty:
        st.info('No songs currently qualify.')
    else:
        def height(x):
            return 0 if pd.isna(x) or x >= 101 else 101 - int(x)

        trend = watch.apply(lambda r: [height(r['rank_w1']), height(r['rank_w2']), height(r['rank_w3']),
                                       height(r['rank_this_week'])], axis=1)
        view = pd.DataFrame({
            'Song': watch['song'], 'Artist': watch['artist_credit'], 'Debuted': watch['debut_date'].map(fmt_date),
            'Trend': trend, 'Debut spot': watch['rank_w1'].map(fmt_rank), 'Spot now': watch['rank_this_week'].map(fmt_rank),
            'Chance of top 10': watch['top10_probability'] * 100,
        })
        st.dataframe(
            view, hide_index=True, width='stretch', height=500,
            column_config={
                'Trend': st.column_config.LineChartColumn(
                    'Trend', y_min=0, y_max=100, width='small',
                    help='Its first 3 weeks plus this week. A rising line means the song is climbing the chart.'),
                'Chance of top 10': st.column_config.ProgressColumn(
                    'Chance of top 10', format='%.1f%%', min_value=0, max_value=25,
                    help='Model estimate. The bar is full at 25%.'),
            })
        st.caption('Think of this as a shortlist, not a guarantee. The scores are good at putting songs in the right '
                   'order but are only rough as exact percentages.')

# ---------------------------------------------------------------- Artist Lookup
with tabs[2]:
    st.subheader('Look up any artist')
    st.caption('See every Hot 100 song an artist has had, as the lead artist or as a featured guest. Some artists break '
               'out by appearing as guests first, then landing hits of their own.')
    artists = q('SELECT artist FROM artists WHERE n_songs >= 2 ORDER BY n_songs DESC, artist')['artist'].tolist()
    who = st.selectbox('Choose or type an artist', artists, index=artists.index('Doja Cat') if 'Doja Cat' in artists else 0)
    a = q('SELECT * FROM artists WHERE artist = ?', [who]).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Hot 100 songs', int(a['n_songs']))
    c2.metric('As lead / as guest', f"{int(a['n_lead'])} / {int(a['n_featured'])}")
    c3.metric('Top 10 hits', int(a['n_top10']))
    c4.metric('First appeared', pd.Timestamp(a['first_chart_date']).strftime('%b %Y'))
    hist = q('''SELECT s.song, s.artist_credit, c.role, s.debut_date, s.peak_rank, s.total_weeks
                FROM credits c JOIN songs s USING (song_id) WHERE c.artist = ? ORDER BY s.debut_date''', [who])
    hist['Role'] = hist['role'].map({'lead': 'lead artist', 'featured': 'featured guest'})
    fig = px.scatter(hist, x='debut_date', y='peak_rank', color='Role', size='total_weeks', size_max=16,
                     color_discrete_map={'lead artist': ACCENT, 'featured guest': BLUE},
                     hover_data={'song': True, 'artist_credit': True, 'total_weeks': True},
                     labels={'debut_date': 'Year the song came out', 'peak_rank': 'Highest spot reached',
                             'song': 'Song', 'artist_credit': 'Credit', 'total_weeks': 'Weeks on chart'})
    fig.update_traces(marker=dict(line=dict(width=0), opacity=0.85))
    start, end = pd.Timestamp(hist['debut_date'].min()), pd.Timestamp(counts['last'])
    pad = max((end - start) * 0.03, pd.Timedelta(days=45))
    fig.update_xaxes(range=[start - pad, end + pd.Timedelta(days=20)])   # stop at the latest chart, no empty future
    show(position_axis(style(fig, height=400)))
    st.caption('Each dot is one song. Higher dots reached better spots; bigger dots stayed on the chart longer. '
               'Hover over a dot for details.')
    st.dataframe(pd.DataFrame({
        'Song': hist['song'], 'Credit': hist['artist_credit'], 'Role': hist['Role'],
        'Came out': hist['debut_date'].map(fmt_date), 'Highest spot': hist['peak_rank'].astype(int).map(lambda v: f'#{v}'),
        'Weeks on chart': hist['total_weeks'].astype(int)}), hide_index=True, width='stretch', height=360)

# ---------------------------------------------------------------- Song History
with tabs[3]:
    st.subheader('Follow a song week by week')
    term = st.text_input('Type a song title', 'Not Like Us', help='Partial titles work too, for example "Blinding".')
    matches = q('''SELECT song_id, song || '  –  ' || artist_credit || '  (' || strftime(debut_date, '%Y') || ')' AS label
                   FROM songs WHERE song ILIKE ? ORDER BY debut_date DESC LIMIT 25''', [f'%{term.strip()}%'])
    if term.strip() and len(matches):
        pick = st.selectbox('Pick the version you mean', matches['label'])
        sid = int(matches.loc[matches['label'] == pick, 'song_id'].iloc[0])
        tr = q('SELECT chart_week, chart_date, rank FROM chart_entries WHERE song_id = ? ORDER BY chart_week', [sid])
        # fill missing weeks so the line breaks when a song leaves the chart instead of bridging the gap
        weeks = q('SELECT DISTINCT chart_week, chart_date FROM chart_entries WHERE chart_week BETWEEN ? AND ? ORDER BY 1',
                  [int(tr['chart_week'].min()), int(tr['chart_week'].max())])
        tr = weeks.merge(tr[['chart_week', 'rank']], on='chart_week', how='left')
        on = tr['rank'].notna()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric('Highest spot', f"#{int(tr['rank'].min())}")
        m2.metric('Weeks on chart', int(on.sum()))
        m3.metric('First week', fmt_date(tr.loc[on, 'chart_date'].min()))
        m4.metric('Last week', fmt_date(tr.loc[on, 'chart_date'].max()))
        fig = px.line(tr, x='chart_date', y='rank', markers=True, color_discrete_sequence=[ACCENT],
                      labels={'chart_date': 'Week', 'rank': 'Chart spot'})
        fig.update_traces(connectgaps=False, marker=dict(size=5))
        show(position_axis(style(fig, height=420)))
        st.caption('Higher on the chart means more popular. A gap means the song dropped off the chart that week.')
    elif term.strip():
        st.info('No songs match that title. Try fewer words.')

# ---------------------------------------------------------------- Does It Work?
with tabs[4]:
    st.subheader('Do the predictions actually come true?')
    st.write('To check, the model was trained only on older songs and then asked to rate newer songs it had never '
             'seen. Then the ratings were compared with what really happened. The comparison point is a simple rule '
             'of thumb: assume songs that debut higher are more likely to reach the top 10.')
    b1, b2 = st.columns(2, gap='large')
    for col, bt, title, sub in [
            (b1, main_bt, 'Test on 2016-2025 songs', 'trained on 1990-2015 songs'),
            (b2, stream_bt, 'Test on 2021-2025 songs', 'trained on 2013-2020 songs (streaming era)')]:
        with col:
            st.markdown(f'**{title}**  \n<span style="color:#A9ADB5">{sub}</span>', unsafe_allow_html=True)
            x1, x2 = st.columns(2)
            x1.metric('Top 50 picks that reached the top 10', f"{bt['model']['precision_top50']:.0%}",
                      f"vs. {bt['baseline_debut_rank']['precision_top50']:.0%} with the rule of thumb", delta_color='off', delta_arrow='off')
            x2.metric('Songs tested', f"{bt['test_songs']:,}",
                      f"only {bt['test_positive_rate']:.1%} reached the top 10", delta_color='off', delta_arrow='off')
    st.info(f"In plain terms: among newer songs that debuted outside the top 10, about 1 in "
            f"{round(1 / main_bt['test_positive_rate'])} eventually made it. Of the 50 songs the model liked most, "
            f"{round(model_hit * 50)} made it.")

    st.subheader('What makes a song more likely to break')
    coef = pd.DataFrame(metrics['standardized_coefficients'].items(), columns=['feature', 'coefficient'])
    names = {'height_w3': 'Higher spot in week 3', 'climb_w1_w3': 'Climbing from week 1 to week 3',
             'climb_w2_w3': 'Climbing from week 2 to week 3', 'prior_songs': 'Artist already has many chart songs',
             'prior_top10': 'Artist already has top 10 hits', 'has_feature': 'Has a featured guest',
             'n_artists': 'More artists credited'}
    coef['feature'] = coef['feature'].map(names)
    coef['effect'] = coef['coefficient'].map(lambda v: 'makes a breakout more likely' if v > 0 else 'makes it less likely')
    fig = px.bar(coef.sort_values('coefficient'), x='coefficient', y='feature', orientation='h', color='effect',
                 color_discrete_map={'makes a breakout more likely': ACCENT, 'makes it less likely': BLUE},
                 labels={'coefficient': 'Strength of effect', 'feature': '', 'effect': ''})
    show(style(fig, height=360))
    st.caption('Longer bars matter more. Artists with lots of chart songs often have many album tracks that briefly '
               'chart and fade, which is why that bar points the other way, while a track record of top 10 hits helps.')

    with st.expander('Details for data-minded readers'):
        rows = []
        for name, bt in [('Train 1990-2015, test 2016-2025', main_bt), ('Train 2013-2020, test 2021-2025', stream_bt)]:
            for label, key in [('Debut position only', 'baseline_debut_rank'), ('Early-trajectory model', 'model')]:
                r = bt[key]
                rows.append({'Test': name, 'Model': label, 'ROC-AUC': f"{r['roc_auc']:.2f}", 'PR-AUC': f"{r['pr_auc']:.2f}",
                             'Precision in top 50': f"{r['precision_top50']:.0%}", 'Test songs': f"{bt['test_songs']:,}",
                             'Positive rate': f"{bt['test_positive_rate']:.1%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        st.caption('Logistic regression on standardized features with time-based train/test splits and no look-ahead. '
                   'Bars above are standardized coefficients from the 1990-2015 model. ROC-AUC measures how well scores '
                   'separate songs that climbed from songs that did not (0.5 = coin flip, 1.0 = perfect).')

# ---------------------------------------------------------------- How It Was Built
with tabs[5]:
    st.markdown('''
#### Where the data comes from
Every weekly Billboard Hot 100 chart, from the public
[mhollingshead/billboard-hot-100](https://github.com/mhollingshead/billboard-hot-100) dataset. The data is loaded into
DuckDB (a fast database) by `pipeline.py`, and SQL queries in `sql/` build the song, artist, and credit tables.
Exact duplicate rows in the source (the same song listed twice in one week) are removed.

#### Telling artists apart
Billboard writes credits as one line of text, which mixes single acts whose names contain commas or "&" ("Earth, Wind & Fire", "Tyler, The
Creator") with collaborations between separate artists ("Future & Metro Boomin"). Names after "Featuring" or "With" are counted as featured guests. A lead
credit is split into separate artists only when at least half of the names also chart on their own and the rest look
like full personal names. Otherwise it is treated as one act.

#### Songs that change credits
Sometimes Billboard adds a guest artist to a song partway through its run. That would make the song look brand new,
so those runs are joined back to the original song (same title and at least one shared artist).

#### How the model works
For each song that debuted outside the top 10, the model looks at its spot in week 3, how much it climbed in weeks 1
to 3 and in week 3 alone, how many chart songs and top 10 hits its main artist had before, and whether it has a
featured guest. It uses logistic regression, a standard statistical method for yes-or-no outcomes. It was always
tested on later years than it learned from. The "Could Break Next" list uses the same method trained on 2013-2025
songs.

#### Limits worth knowing
- One-word guest names stay attached to the credit ("Drake, Don Toliver & Yebba"), and duos whose members also chart
  solo are split ("Sonny & Cher"). The new-artists list skips combined credits that include an established artist.
- Double-sided singles appear the way Billboard printed them, so a song can show up both alone and as part of a pair
  ("Something" and "Come Together/Something").
- Fewer songs climb into the top 10 today (about 3% recently vs. about 15% before 2016), partly because whole albums
  now chart at once through streaming.
- The Hot 100 reacts more slowly than streaming, social media, or Shazam. A real label tool would combine all of them.
''')

st.markdown(f'<div class="footer">Built by <a href="{LINKEDIN}">Sadaf Sarbazi</a>  •  '
            f'<a href="{REPO}">Code, SQL, and tests on GitHub</a>  •  Chart data: '
            '<a href="https://github.com/mhollingshead/billboard-hot-100">mhollingshead/billboard-hot-100</a></div>',
            unsafe_allow_html=True)
