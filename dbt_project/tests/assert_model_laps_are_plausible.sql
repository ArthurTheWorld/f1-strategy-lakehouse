-- tempo de volta positivo e idade do pneu >= 1; falha se algum dado corrompido passar pela limpeza
select race_id, driver, lap_number
from {{ ref('fct_laps_model') }}
where lap_time_s <= 0 or tyre_life < 1
