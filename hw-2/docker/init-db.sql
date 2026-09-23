-- Выполняется один раз при первом старте контейнера postgres
create role dwh login password 'dwh';
create database dwh owner dwh;
create role airflow login password 'airflow';
create database airflow owner airflow;
