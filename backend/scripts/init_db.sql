-- scripts/init_db.sql
-- Runs once when PostgreSQL container starts for the first time.
-- Creates all RiskLake schemas. Tables are created by dbt and Python scripts.

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- dbt needs USAGE on all schemas
GRANT ALL PRIVILEGES ON SCHEMA bronze TO risklake;
GRANT ALL PRIVILEGES ON SCHEMA silver TO risklake;
GRANT ALL PRIVILEGES ON SCHEMA gold   TO risklake;
