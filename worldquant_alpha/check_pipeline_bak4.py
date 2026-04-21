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
    # USA RAM sharpe distribution
    print('=== pipeline_bak_0417 USA RAM sharpe distribution ===')
    r = conn.execute(text("""
        SELECT 
            CASE 
                WHEN sharpe >= 1.58 THEN 'S>=1.58'
                WHEN sharpe >= 1.0 THEN 'S>=1.0'
                WHEN sharpe >= 0.5 THEN 'S>=0.5'
                ELSE 'S<0.5'
            END as sharpe_range,
            COUNT(*)
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND is_tested = TRUE
        GROUP BY sharpe_range
    """))
    for row in r:
        print(f'  {row[0]}: {row[1]}')

    # USA RAM fitness distribution
    print('\n=== pipeline_bak_0417 USA RAM fitness distribution ===')
    r = conn.execute(text("""
        SELECT 
            CASE 
                WHEN fitness >= 1.0 THEN 'F>=1.0'
                WHEN fitness >= 0.5 THEN 'F>=0.5'
                WHEN fitness >= 0.2 THEN 'F>=0.2'
                ELSE 'F<0.2'
            END as fitness_range,
            COUNT(*)
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND is_tested = TRUE
        GROUP BY fitness_range
    """))
    for row in r:
        print(f'  {row[0]}: {row[1]}')

    # USA RAM: both S>=1.58 AND F>=1.0
    print('\n=== pipeline_bak_0417 USA RAM: S>=1.58 AND F>=1.0 ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND sharpe >= 1.58
        AND fitness >= 1.0
        ORDER BY sharpe DESC
        LIMIT 10
    """))
    count = 0
    for row in r:
        count += 1
        expr = row[0] if row[0] else ''
        print(f'{expr}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | {row[4]}')
    if count == 0:
        print('  NONE FOUND')

    # USA RAM: S>=1.0 AND F>=0.8 (close)
    print('\n=== pipeline_bak_0417 USA RAM: S>=1.0 AND F>=0.8 ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color
        FROM pipeline_bak_0417 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND sharpe >= 1.0
        AND fitness >= 0.8
        ORDER BY fitness DESC, sharpe DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        print(f'{expr}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | {row[4]}')

    # Also check pipeline_bak_0419 for good ones
    print('\n=== pipeline_bak_0419 USA: S>=1.0 AND F>=0.8 ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color, candidate_status
        FROM pipeline_bak_0419 
        WHERE settings LIKE '%USA%'
        AND sharpe >= 1.0
        AND fitness >= 0.8
        ORDER BY fitness DESC, sharpe DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        print(f'{expr[:80]}')
        print(f'  S={row[1]} F={row[2]} T={row[3]} | {row[4]} | {row[5]}')
