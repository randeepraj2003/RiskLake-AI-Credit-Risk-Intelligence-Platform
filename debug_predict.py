import sys
sys.path.insert(0, '.')
import os
os.environ['PG_HOST'] = 'localhost'
os.environ['PG_DB'] = 'risklake'
os.environ['PG_USER'] = 'postgres'
os.environ['PG_PASSWORD'] = 'risklake'

import psycopg2

conn = psycopg2.connect(host='localhost', dbname='risklake', user='postgres', password='risklake')
cur = conn.cursor()

# Test the exact query that risk.py runs
cur.execute('''
    SELECT p.application_id, p.customer_id, p.pd_probability_rf,
           p.pd_probability_lr, p.pd_probability_ens, p.pd_prediction,
           p.risk_grade, p.model_version, p.scored_at
    FROM gold.pd_predictions p
    WHERE p.application_id = %s
    ORDER BY p.scored_at DESC LIMIT 1
''', ('APP000001',))

row = cur.fetchone()
print('PD row found:', row)

# Test Silver join query
cur.execute('''
    SELECT d.loan_amount_inr, d.annual_income_inr, d.dti_ratio
    FROM silver_silver.feat_dti_ratio d
    WHERE d.application_id = %s
''', ('APP000001',))
row2 = cur.fetchone()
print('Silver row found:', row2)

conn.close()
print('All queries OK!')
