{% test unique_combination(model, columns) %}
-- Возвращает комбинации столбцов, встречающиеся более одного раза
select {{ columns | join(', ') }}, count(*) as row_count
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
