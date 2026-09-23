{#- Суррогатный ключ DWH: md5 от частей натурального ключа, ВСЕГДА включая source_system -#}
{% macro surrogate_key(cols) -%}
    md5({% for c in cols %}coalesce(cast({{ c }} as text), '∅'){% if not loop.last %} || '|' || {% endif %}{% endfor %})
{%- endmacro %}
