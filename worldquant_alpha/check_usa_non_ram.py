from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os, json

load_dotenv('.env')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'worldquant_alpha')
DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    # USA non-RAM with best sharpe AND fitness
    print('=== USA non-RAM: best sharpe ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, settings
        FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        AND (alpha_expression NOT LIKE '%group_neutralize%' OR alpha_expression IS NULL)
        AND is_tested = TRUE
        ORDER BY sharpe DESC
        LIMIT 15
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        settings = json.dumps(row[5])[:100] if row[5] else ''
        print(f'EXPR: {expr}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | {row[4]}')
        print(f'  settings: {settings}')
        print()

    # USA non-RAM with best fitness
    print('=== USA non-RAM: best fitness ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, settings
        FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        AND (alpha_expression NOT LIKE '%group_neutralize%' OR alpha_expression IS NULL)
        AND is_tested = TRUE
        ORDER BY fitness DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        settings = json.dumps(row[5])[:100] if row[5] else ''
        print(f'EXPR: {expr}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | {row[4]}')
        print(f'  settings: {settings}')
        print()

    # Count non-RAM USA tested
    r = conn.execute(text("""
        SELECT COUNT(*) FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        AND (alpha_expression NOT LIKE '%group_neutralize%' OR alpha_expression IS NULL)
        AND is_tested = TRUE
    """))
    print(f'Total USA non-RAM tested: {r.scalar()}')
