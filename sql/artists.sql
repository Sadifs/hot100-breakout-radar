-- One row per artist (after credit parsing): career start, hit counts, and recent activity.
CREATE OR REPLACE TABLE artists AS
WITH latest AS (SELECT MAX(chart_date) AS d FROM chart_entries),
c AS (
    SELECT c.artist, c.role, s.*
    FROM credits c JOIN songs s USING (song_id)
)
SELECT artist,
       MIN(debut_date)                                                        AS first_chart_date,
       MIN(CASE WHEN role = 'lead' THEN debut_date END)                       AS first_lead_date,
       MAX(last_date)                                                         AS last_chart_date,
       COUNT(*)                                                               AS n_songs,
       SUM(CASE WHEN role = 'lead' THEN 1 ELSE 0 END)                         AS n_lead,
       SUM(CASE WHEN role = 'featured' THEN 1 ELSE 0 END)                     AS n_featured,
       SUM(reached_top10)                                                     AS n_top10,
       MIN(peak_rank)                                                         AS best_peak,
       SUM(CASE WHEN debut_date > (SELECT d FROM latest) - INTERVAL 52 WEEK THEN 1 ELSE 0 END) AS songs_last_52w
FROM c
GROUP BY artist;
