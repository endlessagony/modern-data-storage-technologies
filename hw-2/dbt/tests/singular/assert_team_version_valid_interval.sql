-- История (SCD2): период версии непустой, valid_from < valid_to.
select * from {{ ref('dim_team') }} where valid_from >= valid_to
