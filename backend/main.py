import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))

app = FastAPI(
    title='RiskLake API',
    description='Credit Risk Data Lakehouse',
    version='1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

from app.routers import analyst, risk

app.include_router(risk.router, prefix='/api')
app.include_router(analyst.router, prefix='/api')

@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'risklake-api'}

@app.get('/')
async def root():
    return {'service': 'RiskLake API', 'docs': '/docs', 'health': '/health'}
