-- Song-level features for the backtest and watchlist.
-- Track record = the most established individual lead artist on the song, counting only songs that debuted in
-- EARLIER chart weeks (no look-ahead).
WITH artist_songs AS (
    SELECT c.artist, s.debut_week, s.reached_top10
    FROM credits c JOIN songs s USING (song_id)
),
component_hist AS (
    SELECT lc.song_id, lc.component,
           COUNT(h.artist)                   AS prior_songs,
           COALESCE(SUM(h.reached_top10), 0) AS prior_top10
    FROM lead_components lc
    JOIN songs s USING (song_id)
    LEFT JOIN artist_songs h ON h.artist = lc.component AND h.debut_week < s.debut_week
    GROUP BY lc.song_id, lc.component
),
lead_hist AS (
    SELECT song_id, MAX(prior_songs) AS prior_songs, MAX(prior_top10) AS prior_top10
    FROM component_hist GROUP BY song_id
)
SELECT s.song_id, s.song, s.artist_credit, s.lead_artist, s.debut_date, s.debut_week, s.is_new_entry,
       s.rank_w1, s.rank_w2, s.rank_w3,
       101 - s.rank_w3            AS height_w3,       -- spots above the bottom of the chart in week 3 (higher = better)
       s.rank_w1 - s.rank_w3      AS climb_w1_w3,     -- total climb over the first 3 weeks
       s.rank_w2 - s.rank_w3      AS climb_w2_w3,     -- most recent week's climb
       COALESCE(h.prior_songs, 0) AS prior_songs, COALESCE(h.prior_top10, 0) AS prior_top10,
       s.has_feature, s.n_artists, s.reached_top10
FROM songs s LEFT JOIN lead_hist h USING (song_id)
-- fixed row order so tied scores (e.g., equal debut positions) always rank the same way
ORDER BY s.song_id;
