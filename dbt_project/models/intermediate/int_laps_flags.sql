-- Marca cada volta; quem decide o que entra no modelo é `is_clean`.
-- Limpa = não é a volta 1, tem tempo, não foi anulada, é precisa, pista livre (status exatamente '1')
-- e não é volta de entrada nem de saída dos boxes.
select
    *,
    pit_in_time_s  is not null                                  as is_in_lap,
    pit_out_time_s is not null                                  as is_out_lap,
    track_status = '1'                                          as is_track_clear,
    (
        lap_number > 1
        and lap_time_s is not null
        and not is_deleted
        and is_accurate
        and track_status = '1'
        and pit_in_time_s is null
        and pit_out_time_s is null
    )                                                           as is_clean
from {{ ref('stg_laps') }}
