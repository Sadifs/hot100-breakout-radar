"""Checks for the credit parser and for the built database. Run:  pytest -q"""
from pathlib import Path

import duckdb
import pytest

from pipeline import build_credit_parser, normalize_title

DB = Path(__file__).resolve().parents[1] / 'data' / 'processed' / 'hot100.duckdb'

# a small universe of credits standing in for the full chart
CREDITS = [
    'Drake', 'Future', 'Metro Boomin', 'Cher', 'Sonny', 'Tina Turner', 'Olivia Rodrigo', 'Smokey Robinson', 'The Miracles',
    'Earth, Wind & Fire', 'Tyler, The Creator', 'Simon & Garfunkel', 'Garfunkel', 'Future & Metro Boomin',
    'Drake Featuring Future & Molly Santana', 'Ike & Tina Turner', 'Olivia Rodrigo & Robert Smith',
    'Smokey Robinson & The Miracles', 'Sonny & Cher', 'Kool & The Gang',
]
parse = build_credit_parser(CREDITS)


def names(credit):
    return [a for a, _ in parse(credit)]


@pytest.mark.parametrize('credit', ['Earth, Wind & Fire', 'Tyler, The Creator', 'Simon & Garfunkel', 'Kool & The Gang',
                                    'Ike & Tina Turner'])
def test_acts_stay_whole(credit):
    assert names(credit) == [credit]


def test_collaborations_split():
    assert names('Future & Metro Boomin') == ['Future', 'Metro Boomin']
    assert names('Olivia Rodrigo & Robert Smith') == ['Olivia Rodrigo', 'Robert Smith']


def test_featured_roles():
    assert parse('Drake Featuring Future & Molly Santana') == [
        ('Drake', 'lead'), ('Future', 'featured'), ('Molly Santana', 'featured')]


def test_normalize_title():
    assert normalize_title("Born In The U.S.A.") == normalize_title('born in the usa')


@pytest.fixture(scope='module')
def con():
    if not DB.exists():
        pytest.skip('database not built; run python pipeline.py')
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def test_one_row_per_song_per_week(con):
    assert one(con, 'SELECT COUNT(*) FROM (SELECT song_id, chart_week FROM chart_entries GROUP BY 1, 2 HAVING COUNT(*) > 1)') == 0


def test_ranks_in_range(con):
    assert one(con, 'SELECT COUNT(*) FROM chart_entries WHERE rank NOT BETWEEN 1 AND 100') == 0


def test_chart_weeks_are_consecutive(con):
    assert one(con, 'SELECT MAX(chart_week) + 1 - COUNT(DISTINCT chart_week) FROM chart_entries') == 0


def test_every_song_has_a_lead_artist(con):
    assert one(con, "SELECT COUNT(*) FROM songs s WHERE NOT EXISTS (SELECT 1 FROM credits c WHERE c.song_id = s.song_id AND c.role = 'lead')") == 0


def test_song_table_is_consistent(con):
    assert one(con, 'SELECT COUNT(*) FROM songs WHERE peak_rank > rank_w1 OR total_weeks < 1') == 0


def test_no_look_ahead_in_track_record(con):
    # if every lead artist on a song first charted in that same week, its track record must be zero
    features = (DB.parents[2] / 'sql' / 'backtest_features.sql').read_text().strip().rstrip(';')
    sql = f"""WITH f AS ({features}),
              first_week AS (SELECT c.artist, MIN(s.debut_week) AS w FROM credits c JOIN songs s USING (song_id) GROUP BY 1),
              all_new AS (SELECT lc.song_id, BOOL_AND(fw.w = s.debut_week) AS every_lead_new
                          FROM lead_components lc JOIN songs s USING (song_id) JOIN first_week fw ON fw.artist = lc.component
                          GROUP BY lc.song_id)
              SELECT COUNT(*) FROM f JOIN all_new USING (song_id) WHERE every_lead_new AND (f.prior_songs > 0 OR f.prior_top10 > 0)"""
    assert one(con, sql) == 0
