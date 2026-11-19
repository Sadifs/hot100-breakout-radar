-- Artists whose FIRST Hot 100 credit came in the last 26 chart weeks, with their best peak and this week's movement.
WITH latest AS (SELECT MAX(chart_week) AS w FROM chart_entries),
artist_start AS (
    SELECT c.artist, MIN(s.debut_week) AS first_week
    FROM credits c JOIN songs s USING (song_id)
    GROUP BY c.artist
),
this_week AS (
    SELECT c.artist, MIN(e.rank) AS best_rank_this_week,
           MAX(e.last_week - e.rank) AS biggest_gain_this_week
    FROM chart_entries e JOIN credits c USING (song_id)
    WHERE e.chart_week = (SELECT w FROM latest)
    GROUP BY c.artist
)
SELECT a.artist, a.first_chart_date, a.n_songs, a.n_lead, a.n_featured, a.best_peak,
       t.best_rank_this_week, t.biggest_gain_this_week
FROM artists a
JOIN artist_start st USING (artist)
LEFT JOIN this_week t USING (artist)
WHERE st.first_week > (SELECT w FROM latest) - 26
ORDER BY a.best_peak, a.n_songs DESC, a.artist;
