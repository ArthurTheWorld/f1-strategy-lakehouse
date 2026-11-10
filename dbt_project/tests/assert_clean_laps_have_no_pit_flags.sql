select race_id, driver, lap_number
from {{ ref('int_laps_flags') }}
where is_clean and (is_in_lap or is_out_lap or track_status <> '1' or lap_number = 1)
