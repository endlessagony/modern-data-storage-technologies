{% test value_between(model, column_name, min_value, max_value) %}
-- Возвращает строки, где значение вне допустимого диапазона [min_value, max_value]
select *
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}
