import psycopg2

conn = psycopg2.connect(host='localhost',dbname='risklake',user='postgres',password='risklake')
cur = conn.cursor()
cur.execute('SELECT model_version, status, ensemble_auc FROM gold.model_registry ORDER BY registered_at')
for r in cur.fetchall():
    print(r)
conn.close()
