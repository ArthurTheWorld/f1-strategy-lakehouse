-- Marca cada volta; quem decide o que entra no modelo é `is_clean`.
-- Limpa = não é a volta 1, tem tempo, não foi anulada, é precisa, pista livre (status exatamente '1'),
-- não é volta de entrada nem de saída dos boxes e o pelotão inteiro não estava lento naquela volta.
--
-- A última regra existe porque o TrackStatus pode vir '1' numa volta neutralizada: em Suzuka 2024, a volta
-- da relargada depois da bandeira vermelha levou ~149 s com status '1'. Se a mediana do pelotão numa volta
-- passa 5% do ritmo base da corrida, a volta inteira sai do modelo.
with base as (
    select
        *,
        pit_in_time_s  is not null                              as is_in_lap,
        pit_out_time_s is not null                              as is_out_lap,
        track_status = '1'                                      as is_track_clear,
        (
            lap_number > 1
            and lap_time_s is not null
            and not is_deleted
            and is_accurate
            and track_status = '1'
            and pit_in_time_s is null
            and pit_out_time_s is null
        )                                                       as passes_lap_rules
    from {{ ref('stg_laps') }}
),

field_by_lap as (
    select race_id, lap_number, median(lap_time_s) as field_median_lap_s
    from base
    where passes_lap_rules
    group by 1, 2
),

field_by_race as (
    select race_id, median(lap_time_s) as race_median_lap_s
    from base
    where passes_lap_rules
    group by 1
)

select
    b.* exclude (passes_lap_rules),
    coalesce(l.field_median_lap_s > 1.05 * r.race_median_lap_s, false) as is_field_slow_lap,
    b.passes_lap_rules
    and not coalesce(l.field_median_lap_s > 1.05 * r.race_median_lap_s, false) as is_clean
from base b
left join field_by_lap l using (race_id, lap_number)
left join field_by_race r using (race_id)
