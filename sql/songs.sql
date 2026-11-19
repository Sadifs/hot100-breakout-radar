-- One row per song: debut, early trajectory (by chart week, not calendar days), peak, and top-10 outcome.
-- is_new_entry = 1 when the song's first week in this data is a true Hot 100 debut (weeks_on_chart = 1),
-- which excludes songs already mid-run when the data begins.
CREATE OR REPLACE TABLE songs AS
WITH first_week AS (
    SELECT song_id, MIN(chart_week) AS debut_week FROM chart_entries GROUP BY song_id
),
traj AS (
    SELECT e.song_id, f.debut_week,
           MIN(e.chart_date)                                                          AS debut_date,
           MAX(CASE WHEN e.chart_week = f.debut_week THEN e.rank END)                 AS rank_w1,
           MAX(CASE WHEN e.chart_week = f.debut_week + 1 THEN e.rank END)             AS rank_w2,
           MAX(CASE WHEN e.chart_week = f.debut_week + 2 THEN e.rank END)             AS rank_w3,
           MAX(CASE WHEN e.chart_week = f.debut_week THEN e.weeks_on_chart END)       AS woc_at_debut,
           MIN(e.rank)                                                                AS peak_rank,
           COUNT(*)                                                                   AS total_weeks,
           MAX(e.chart_date)                                                          AS last_date,
           ARG_MAX(e.artist_credit, e.chart_week)                                     AS artist_credit,
           ARG_MAX(e.song, e.chart_week)                                              AS song
    FROM chart_entries e JOIN first_week f USING (song_id)
    GROUP BY e.song_id, f.debut_week
),
peak AS (
    SELECT song_id, MIN(chart_date) AS peak_date
    FROM chart_entries e JOIN traj t USING (song_id)
    WHERE e.rank = t.peak_rank
    GROUP BY song_id
),
lead AS (
    SELECT song_id, artist AS lead_artist FROM credits WHERE credit_order = 0
),
ncred AS (
    SELECT song_id, COUNT(*) AS n_artists, MAX(CASE WHEN role = 'featured' THEN 1 ELSE 0 END) AS has_feature
    FROM credits GROUP BY song_id
)
SELECT t.song_id, t.song, t.artist_credit, l.lead_artist, n.n_artists, n.has_feature,
       t.debut_date, t.debut_week, (t.woc_at_debut = 1)::INT AS is_new_entry,
       t.rank_w1,
       COALESCE(t.rank_w2, 101) AS rank_w2,
       COALESCE(t.rank_w3, 101) AS rank_w3,
       t.peak_rank, p.peak_date, t.total_weeks, t.last_date,
       DATE_DIFF('week', t.debut_date, p.peak_date) AS weeks_to_peak,
       (t.peak_rank <= 10)::INT AS reached_top10
FROM traj t JOIN peak p USING (song_id) JOIN lead l USING (song_id) JOIN ncred n USING (song_id);
