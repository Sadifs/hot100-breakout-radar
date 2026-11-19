"""
Hot 100 Breakout Radar: data pipeline.

Builds a DuckDB database from weekly Billboard Hot 100 charts (1958 to present):
  chart_entries  one row per song per chart week (with a chart_week index)
  credits        one row per song per credited artist (lead or featured), after credit parsing
  songs          one row per song with debut, early trajectory, peak, and top-10 outcome
  artists        one row per artist with first chart week and hit counts
  lead_components  one row per song per individual lead artist (used for track-record features)

Two identity problems are handled here:

1. Artist credits. Billboard credits mix acts ("Earth, Wind & Fire", "Tyler, The Creator") with collaborations
   ("Future & Metro Boomin", "Drake Featuring Future"). Text after "Featuring" / "With" becomes featured credits.
   The lead part is split on ", " / " & " / " X " / " x " / " And " when at least half of the pieces are standalone
   chart artists and every other piece looks like a full personal name (2+ words, not "The ..."); otherwise the
   credit is kept whole as one act.

2. Songs whose credit changes mid-run. When Billboard adds a featured artist or re-credits a song, the new credit
   arrives with weeks_on_chart > 1. Such a run is merged back into the earlier song with the same normalized
   title and at least one shared artist, so it is not mistaken for a new debut.

Run:  python pipeline.py
Input: data/raw/hot100_all.json, downloaded automatically from github.com/mhollingshead/billboard-hot-100
"""
import json
import re
import urllib.request
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'data' / 'raw' / 'hot100_all.json'
RAW_URL = 'https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json'
DB = ROOT / 'data' / 'processed' / 'hot100.duckdb'
SQL = ROOT / 'sql'

FEAT = re.compile(r'\s+(?:Featuring|Feat\.|featuring|With)\s+')
SEP = re.compile(r'(, | & | X | x | And )')


def load_entries():
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(RAW_URL, RAW)
    weeks = json.loads(RAW.read_text())
    rows = []
    for w in weeks:
        for e in w['data']:
            rows.append({
                'chart_date': w['date'], 'song': e['song'].strip(), 'artist_credit': e['artist'].strip(),
                'rank': e['this_week'], 'last_week': e['last_week'], 'peak_position': e['peak_position'],
                'weeks_on_chart': e['weeks_on_chart'],
            })
    df = pd.DataFrame(rows)
    df['chart_date'] = pd.to_datetime(df['chart_date'])
    # the source has a few exact duplicates (same song and credit twice in one week): keep the better rank
    df = df.sort_values('rank').drop_duplicates(['chart_date', 'song', 'artist_credit']).sort_values(['chart_date', 'rank'])
    weeks_index = {d: i for i, d in enumerate(sorted(df['chart_date'].unique()))}
    df['chart_week'] = df['chart_date'].map(weeks_index)
    return df.reset_index(drop=True)


def build_credit_parser(credits):
    """Return parse(credit) -> [(artist, 'lead' | 'featured'), ...] using every credit string seen on the chart."""
    leads = {FEAT.split(c)[0] for c in credits}
    known = {c for c in leads if not SEP.search(c)}          # credits that are one artist on their own

    def split_lead(lead):
        parts = SEP.split(lead)
        tokens, seps = parts[0::2], parts[1::2]
        n = len(tokens)
        if n == 1:
            return [lead]

        @lru_cache(maxsize=None)
        def best(i):
            # segment tokens[i:] into pieces: a known artist (may span separators) or a single unknown token;
            # returns (known_count, pieces) maximizing known_count, then preferring fewer pieces
            if i == n:
                return (0, ())
            options = []
            for j in range(n, i, -1):
                name = tokens[i]
                for k in range(i + 1, j):
                    name += seps[k - 1] + tokens[k]
                if name in known:
                    kc, rest = best(j)
                    options.append((kc + 1, (name,) + rest))
            kc, rest = best(i + 1)
            options.append((kc, (tokens[i],) + rest))
            return max(options, key=lambda o: (o[0], -len(o[1])))

        known_count, pieces = best(0)
        unknown = [p for p in pieces if p not in known]
        # an unknown piece may only be split off if it looks like a person's full name (2+ words, not "The ...")
        name_like = all(len(p.split()) >= 2 and not p.startswith(('The ', 'His ', 'Her ')) for p in unknown)
        if len(pieces) > 1 and known_count * 2 >= len(pieces) and name_like:
            return list(pieces)
        return [lead]

    def parse(credit):
        pieces = FEAT.split(credit)
        out = [(a, 'lead') for a in split_lead(pieces[0])]
        for p in pieces[1:]:
            for a in split_lead(p):
                out.append((a, 'featured'))
        seen, uniq = set(), []
        for a, r in out:
            if a not in seen:
                seen.add(a)
                uniq.append((a, r))
        return uniq

    return parse


def normalize_title(title):
    return re.sub(r'[^a-z0-9]', '', title.lower())


def assign_song_ids(entries, parse):
    """Group chart rows into songs, merging credit-change continuations into the earlier song."""
    entries['variant_id'] = entries.groupby(['song', 'artist_credit']).ngroup()
    first = (entries.sort_values('chart_week').groupby('variant_id')
             .agg(song=('song', 'first'), credit=('artist_credit', 'first'), first_week=('chart_week', 'min'),
                  last_week_seen=('chart_week', 'max'), woc_first=('weeks_on_chart', 'first')))
    first['title_key'] = first['song'].map(normalize_title)
    first['artists'] = first['credit'].map(lambda c: {a for a, _ in parse(c)})

    canonical = {v: v for v in first.index}

    def root(v):
        while canonical[v] != v:
            v = canonical[v]
        return v

    by_title = first.reset_index().groupby('title_key')
    for _, grp in by_title:
        if len(grp) < 2:
            continue
        grp = grp.sort_values('first_week')
        for r in grp.itertuples():
            if r.woc_first <= 1:
                continue
            # candidates: same title, started earlier, share at least one artist
            cands = grp[(grp['first_week'] < r.first_week) & grp['artists'].map(lambda s: bool(s & r.artists))]
            if len(cands):
                # prefer the run that ended most recently before this one began
                prev = cands.sort_values('last_week_seen').iloc[-1]['variant_id']
                canonical[r.variant_id] = root(prev)

    entries['song_id'] = entries['variant_id'].map(root)
    merged = int((entries['song_id'] != entries['variant_id']).groupby(entries['variant_id']).any().sum())
    # after merging, a song can appear twice in one week only if the source listed both credits: keep the better rank
    entries = entries.sort_values('rank').drop_duplicates(['chart_date', 'song_id']).sort_values(['chart_week', 'rank'])
    return entries.reset_index(drop=True), merged


def build_credits(entries, parse):
    """One row per song per artist across all credit variants; an artist is 'lead' if lead in any variant."""
    variants = entries[['song_id', 'artist_credit', 'chart_week']].sort_values('chart_week').drop_duplicates(['song_id', 'artist_credit'])
    rows = []
    for r in variants.itertuples():
        for order, (artist, role) in enumerate(parse(r.artist_credit)):
            rows.append({'song_id': r.song_id, 'artist': artist, 'role': role, 'credit_order': order, 'seen_week': r.chart_week})
    c = pd.DataFrame(rows)
    c['is_lead'] = (c['role'] == 'lead').astype(int)
    out = (c.sort_values(['seen_week', 'credit_order'])
           .groupby(['song_id', 'artist'], as_index=False)
           .agg(is_lead=('is_lead', 'max'), credit_order=('credit_order', 'first'), seen_week=('seen_week', 'first')))
    out['role'] = out['is_lead'].map({1: 'lead', 0: 'featured'})
    # stable order: first credit seen for the song, then position within that credit
    out = out.sort_values(['song_id', 'seen_week', 'credit_order']).reset_index(drop=True)
    out['credit_order'] = out.groupby('song_id').cumcount()
    return out[['song_id', 'artist', 'role', 'credit_order']]


def build_lead_components(credits):
    """Map each song to the individual artists behind its lead credit(s), for track-record features.
    A lead credit the parser kept whole ("Drake, Don Toliver & Yebba") is broken into any pieces that chart solo."""
    solo = {a for a in credits['artist'].unique() if not SEP.search(a)}
    rows = []
    for r in credits[credits['role'] == 'lead'].itertuples():
        parts = [p for p in SEP.split(r.artist)[0::2] if p in solo] if SEP.search(r.artist) else []
        for comp in (parts or [r.artist]):
            rows.append({'song_id': r.song_id, 'component': comp})
    return pd.DataFrame(rows).drop_duplicates()


def main():
    entries = load_entries()
    parse = build_credit_parser(entries['artist_credit'].unique())
    entries, merged = assign_song_ids(entries, parse)
    credits = build_credits(entries, parse)
    lead_components = build_lead_components(credits)

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    # register under distinct names so the new DataFrames, not existing tables, are read on rebuilds
    con.register('entries_df', entries.drop(columns=['variant_id']))
    con.register('credits_df', credits)
    con.register('lead_components_df', lead_components)
    con.execute('CREATE OR REPLACE TABLE chart_entries AS SELECT * FROM entries_df')
    con.execute('CREATE OR REPLACE TABLE credits AS SELECT * FROM credits_df')
    con.execute('CREATE OR REPLACE TABLE lead_components AS SELECT * FROM lead_components_df')
    con.execute((SQL / 'songs.sql').read_text())
    con.execute((SQL / 'artists.sql').read_text())
    for t in ['chart_entries', 'credits', 'songs', 'artists']:
        print(f"{t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,} rows")
    multi = con.execute('SELECT COUNT(*) FROM (SELECT song_id FROM credits GROUP BY 1 HAVING COUNT(*) > 1)').fetchone()[0]
    print(f'credit-change runs merged into earlier songs: {merged:,}')
    print(f'songs with 2+ credited artists after parsing: {multi:,}')
    con.close()


if __name__ == '__main__':
    main()
