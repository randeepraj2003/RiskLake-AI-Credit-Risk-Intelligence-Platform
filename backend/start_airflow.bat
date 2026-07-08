@echo off
call set_env.bat
REM RiskLake — Start Airflow (Windows, no Docker)
REM Run this every time you want to use Airflow
REM File: backend/start_airflow.bat

REM Set environment variables
set AIRFLOW_HOME=%~dp0airflow_home
set AIRFLOW__CORE__DAGS_FOLDER=%~dp0dags
set AIRFLOW__CORE__EXECUTOR=LocalExecutor
set AIRFLOW__CORE__LOAD_EXAMPLES=False
set PG_HOST=localhost
set PG_PORT=5432
set PG_DB=risklake
set PG_USER=postgres
set RISKLAKE_ROOT=%~dp0

echo Starting Airflow webserver on http://localhost:8080
echo Starting Airflow scheduler...
echo Login: admin / admin
echo.

REM Start scheduler in background
start "Airflow Scheduler" cmd /k "airflow scheduler"

REM Start webserver
airflow webserver --port 8080
