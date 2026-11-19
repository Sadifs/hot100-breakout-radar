-- Biggest week-over-week climbers on the latest chart among songs 8 weeks old or younger.
WITH latest AS (SELECT MAX(chart_week) AS w FROM chart_entries)
SELECT e.song, e.artist_credit, e.rank, e.last_week, e.last_week - e.rank AS spots_gained,
       e.weeks_on_chart, e.peak_position
FROM chart_entries e
WHERE e.chart_week = (SELECT w FROM latest) AND e.last_week IS NOT NULL AND e.weeks_on_chart <= 8
  AND e.last_week > e.rank
ORDER BY spots_gained DESC, e.rank
LIMIT 15;
