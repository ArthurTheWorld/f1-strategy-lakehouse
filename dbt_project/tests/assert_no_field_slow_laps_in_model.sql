-- Conferência independente no Gold: nenhuma volta do modelo pode vir de uma volta em que o pelotão inteiro
-- estava mais de 5% acima do ritmo base (relargada, safety car mal marcado). Falha listando a corrida e a volta.
select race_id, lap_number, median(lap_time_s) as field_median_lap_s, max(race_median_lap_s) as race_median_lap_s
from {{ ref('fct_laps_model') }}
group by 1, 2
having median(lap_time_s) > 1.05 * max(race_median_lap_s)
