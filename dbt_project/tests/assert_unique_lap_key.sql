-- a chave natural de uma volta é (corrida, piloto, número da volta)
select race_id, driver, lap_number, count(*) as n
from {{ ref('stg_laps') }}
group by 1, 2, 3
having count(*) > 1
