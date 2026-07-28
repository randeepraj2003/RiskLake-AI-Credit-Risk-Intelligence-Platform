import psycopg2

conn = psycopg2.connect(host='localhost',dbname='risklake',user='postgres',password='risklake')
cur = conn.cursor()
cur.execute("UPDATE gold.model_registry SET status='retired' WHERE status='active'")
cur.execute("UPDATE gold.model_registry SET status='active' WHERE model_version='v20260704_2011'")
conn.commit()
print('Promoted v20260704_2011 to active!')
cur.execute('SELECT model_version, status, ensemble_auc FROM gold.model_registry ORDER BY registered_at')
for r in cur.fetchall():
    print(r)
conn.close()
