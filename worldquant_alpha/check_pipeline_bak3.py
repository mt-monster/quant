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
    # High sharpe USA RAM from pipeline_bak_0417
    print('=== pipeline_bak_0417: USA RAM high sharpe (full expressions) ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, settings, backtested_at
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND sharpe > 1.3
        ORDER BY sharpe DESC
        LIMIT 20
    """))
    for row in r:
        expr = row[0]
        settings = json.dumps(row[5]) if row[5] else '{}'
        print(f'EXPR: {expr}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | color={row[4]} | {row[6]}')
        print(f'  settings: {settings[:150]}')
        print()

    # Also check non-RAM but USA high sharpe
    print('=== pipeline_bak_0417: USA non-RAM high sharpe ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color
        FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        AND sharpe > 1.3
        AND (alpha_expression NOT LIKE '%group_neutralize%' OR alpha_expression IS NULL)
        ORDER BY sharpe DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        print(f'{expr[:80]} | S={row[1]} F={row[2]} T={row[3]} | {row[4]}')

    # Count by sharpe range
    print('\n=== pipeline_bak_0417 USA RAM sharpe distribution ===')
    r = conn.execute(text("""
        SELECT 
            CASE 
                WHEN sharpe >= 1.58 THEN 'S>=1.58'
                WHEN sharpe >= 1.0 THEN 'S>=1.0'
                WHEN sharpe >= 0.5 THEN 'S>=0.5'
                ELSE 'S<0.5'
            END as range,
            COUNT(*)
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND is_tested = TRUE
        GROUP BY range
    """))
    for row in r:
        print(f'  {row[0]}: {row[1]}')
