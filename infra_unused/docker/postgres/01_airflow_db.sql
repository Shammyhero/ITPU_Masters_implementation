-- Separate metadata database for Airflow so pipeline bookkeeping never
-- mixes with the canonical benchmark_runs results in the 'airs' database.
CREATE DATABASE airflow OWNER airs;
