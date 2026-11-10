with clean as (
    select race_id, median(lap_time_s) as race_median_lap_s, count(*) as n_clean_laps
    from {{ ref('int_laps_flags') }}
    where is_clean and compound in ('SOFT', 'MEDIUM', 'HARD')
    group by 1
)
select r.race_id, r.year, r.round, r.circuit, r.n_laps, r.source,
       c.race_median_lap_s, c.n_clean_laps
from {{ source('bronze', 'races') }} r
left join clean c using (race_id)
