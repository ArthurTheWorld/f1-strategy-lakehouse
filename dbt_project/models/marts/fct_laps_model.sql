-- Gold: uma linha por volta limpa de pneu seco, com o alvo do modelo normalizado pela corrida.
-- lap_delta_s = tempo da volta - mediana das voltas limpas da corrida (remove circuito e ritmo base).
select
    f.race_id, f.driver, f.lap_number, f.stint, f.compound, f.tyre_life, f.fresh_tyre,
    f.lap_time_s, d.race_median_lap_s,
    f.lap_time_s - d.race_median_lap_s as lap_delta_s,
    f.speed_i1, f.speed_i2, f.speed_fl, f.speed_st
from {{ ref('int_laps_flags') }} f
join {{ ref('dim_races') }} d using (race_id)
where f.is_clean and f.compound in ('SOFT', 'MEDIUM', 'HARD')
