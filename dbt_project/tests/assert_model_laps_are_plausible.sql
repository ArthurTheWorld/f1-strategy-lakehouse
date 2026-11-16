-- tempo de volta positivo, idade do pneu >= 1 e nenhuma volta mais de 30% acima do ritmo base;
-- falha se algum dado corrompido ou volta de incidente passar pela limpeza
select race_id, driver, lap_number
from {{ ref('fct_laps_model') }}
where lap_time_s <= 0 or tyre_life < 1 or lap_time_s > 1.30 * race_median_lap_s
