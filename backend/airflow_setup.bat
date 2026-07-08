@echo off
call set_env.bat
REM RiskLake — Airflow Setup Script for Windows (no Docker)
REM Run this once to install and initialise Airflow
REM File: backend/airflow_setup.bat

echo ========================================
echo RiskLake Airflow Setup (Windows, no Docker)
echo ========================================

REM Step 1: Set Airflow home inside project
set AIRFLOW_HOME=%~dp0airflow_home
set AIRFLOW__CORE__DAGS_FOLDER=%~dp0dags
set AIRFLOW__CORE__EXECUTOR=LocalExecutor
set AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://postgres:risklake@localhost:5432/risklake
set AIRFLOW__CORE__LOAD_EXAMPLES=False

echo AIRFLOW_HOME set to: %AIRFLOW_HOME%

REM Step 2: Install Airflow
echo Installing Apache Airflow...
pip install "apache-airflow==2.9.1" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.1/constraints-3.11.txt"

REM Step 3: Initialise DB
echo Initialising Airflow database...
airflow db migrate

REM Step 4: Create admin user
echo Creating admin user...
airflow users create ^
    --username admin ^
    --password admin ^
    --firstname Randeep ^
    --lastname Raj ^
    --role Admin ^
    --email randeep@risklake.dev

echo ========================================
echo Setup complete!
echo Run start_airflow.bat to start Airflow
echo ========================================
