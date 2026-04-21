from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv('.env')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'worldquant_alpha')
DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    # pipeline_bak_0419 - USA related
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, candidate_status, backtested_at
        FROM pipeline_bak_0419 
        WHERE settings LIKE '%USA%'
        ORDER BY sharpe DESC
        LIMIT 20
    """))
    print('=== pipeline_bak_0419 USA ===')
    for row in r:
        expr = row[0][:60] if row[0] else ''
        print(f'{expr:60s} | S={row[1]} F={row[2]} T={row[3]} | {row[4]} | {row[5]}')
    
    r = conn.execute(text("SELECT COUNT(*) FROM pipeline_bak_0419 WHERE settings LIKE '%USA%'"))
    print(f'USA count in 0419: {r.scalar()}')
    
    # pipeline_bak_0417 - USA related
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, backtested_at
        FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        ORDER BY sharpe DESC
        LIMIT 10
    """))
    print('\n=== pipeline_bak_0417 USA ===')
    for row in r:
        expr = row[0][:60] if row[0] else ''
        print(f'{expr:60s} | S={row[1]} F={row[2]} T={row[3]} | {row[4]}')
    
    r = conn.execute(text("SELECT COUNT(*) FROM pipeline_bak_0417 WHERE settings LIKE '%USA%'"))
    print(f'USA count in 0417: {r.scalar()}')
