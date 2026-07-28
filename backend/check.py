import psycopg2

conn = psycopg2.connect(host='localhost',dbname='risklake',user='postgres',password='risklake')
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='gold'")
print('Gold tables:', cur.fetchall())
cur.execute("SELECT COUNT(*) FROM gold.pd_predictions")
print('PD predictions:', cur.fetchone()[0])
cur.execute("SELECT application_id FROM gold.pd_predictions LIMIT 5")
print('Sample app IDs:', cur.fetchall())
conn.close()
