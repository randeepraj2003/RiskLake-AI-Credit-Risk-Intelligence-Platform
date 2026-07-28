import os
import sys

sys.path.insert(0, '.')
os.environ['PG_HOST'] = 'localhost'
os.environ['PG_DB'] = 'risklake'
os.environ['PG_USER'] = 'postgres'
os.environ['PG_PASSWORD'] = 'risklake'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'

try:
    from app.routers.risk import router
    print('Router imported OK')
except Exception as e:
    print('Router import error:', e)
    import traceback
    traceback.print_exc()

try:
    from app.services.inference import predict
    print('Inference imported OK')
except Exception as e:
    print('Inference import error:', e)
    import traceback
    traceback.print_exc()
