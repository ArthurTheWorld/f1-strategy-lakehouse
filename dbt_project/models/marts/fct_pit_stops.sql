-- Uma linha por parada com volta de entrada e de saída ambas sob pista livre e com tempo válido.
-- Paradas sob safety car/VSC ficam de fora (custam bem menos e distorceriam a perda média).
with pairs as (
    select
        i.race_id, i.driver,
        i.lap_number    as in_lap,     i.compound as compound_before, i.tyre_life as tyre_life_in,
        i.lap_time_s    as in_lap_time_s, i.track_status as in_status,
        o.lap_number    as out_lap,    o.compound as compound_after,  o.tyre_life as tyre_life_out,
        o.lap_time_s    as out_lap_time_s, o.track_status as out_status
    from {{ ref('int_laps_flags') }} i
    join {{ ref('int_laps_flags') }} o
      on o.race_id = i.race_id and o.driver = i.driver and o.lap_number = i.lap_number + 1
    where i.is_in_lap and o.is_out_lap
)
select
    p.race_id, p.driver, p.in_lap, p.out_lap,
    p.compound_before, p.compound_after, p.tyre_life_in, p.tyre_life_out,
    p.in_lap_time_s, p.out_lap_time_s,
    p.in_lap_time_s  - d.race_median_lap_s as in_lap_delta_s,
    p.out_lap_time_s - d.race_median_lap_s as out_lap_delta_s
from pairs p
join {{ ref('dim_races') }} d using (race_id)
where p.in_status = '1' and p.out_status = '1'
  and p.in_lap_time_s is not null and p.out_lap_time_s is not null
  and p.compound_before in ('SOFT', 'MEDIUM', 'HARD') and p.compound_after in ('SOFT', 'MEDIUM', 'HARD')
