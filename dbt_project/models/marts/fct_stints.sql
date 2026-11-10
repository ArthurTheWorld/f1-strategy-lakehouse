select
    f.race_id, f.driver, f.stint,
    max(f.compound)                          as compound,
    min(f.lap_number)                        as start_lap,
    max(f.lap_number)                        as end_lap,
    count(*)                                 as n_laps,
    min(f.tyre_life)                         as start_tyre_life,
    bool_and(f.fresh_tyre)                   as started_on_fresh_tyres,
    avg(m.lap_delta_s)                       as mean_clean_delta_s,
    count(m.lap_number)                      as n_clean_laps
from {{ ref('int_laps_flags') }} f
left join {{ ref('fct_laps_model') }} m
  on m.race_id = f.race_id and m.driver = f.driver and m.lap_number = f.lap_number
group by f.race_id, f.driver, f.stint
