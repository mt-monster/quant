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
    # Check pipeline_alphas_bak: top sharpe
    print('=== pipeline_alphas_bak: top sharpe records ===')
    r = conn.execute(text('''
        SELECT alpha_expression, sharpe, fitness, turnover, color, stage, backtest_status, settings
        FROM pipeline_alphas_bak 
        WHERE is_tested = TRUE
        ORDER BY sharpe DESC
        LIMIT 20
    '''))
    for row in r:
        expr = row[0][:60] if row[0] else ''
        print(f'{expr:60s} | S={row[1]} F={row[2]} T={row[3]} | {row[4]} | {row[5]} | {row[6]}')
    
    # Count tested in bak
    r = conn.execute(text('SELECT COUNT(*) FROM pipeline_alphas_bak WHERE is_tested = TRUE'))
    print(f'\nTested in bak: {r.scalar()}')
    
    # Count by stage
    print('\n=== Stages in pipeline_alphas_bak ===')
    r = conn.execute(text('SELECT stage, COUNT(*) FROM pipeline_alphas_bak GROUP BY stage'))
    for row in r:
        print(f'  {row[0]}: {row[1]}')
    
    # USA related
    print('\n=== USA related in pipeline_alphas_bak ===')
    r = conn.execute(text("SELECT COUNT(*) FROM pipeline_alphas_bak WHERE settings LIKE '%USA%'"))
    print(f'  USA count: {r.scalar()}')
    
    # RAM related
    r = conn.execute(text("SELECT COUNT(*) FROM pipeline_alphas_bak WHERE alpha_expression LIKE '%group_neutralize%' AND settings LIKE '%USA%'"))
    print(f'  USA+RAM count: {r.scalar()}')
    
    # High sharpe USA RAM
    print('\n=== USA RAM with sharpe > 1.0 ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color
        FROM pipeline_alphas_bak 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND sharpe > 1.0
        ORDER BY sharpe DESC
        LIMIT 15
    """))
    for row in r:
        expr = row[0][:70] if row[0] else ''
        print(f'{expr:70s} | S={row[1]} F={row[2]} T={row[3]} | {row[4]}')

    # USA RAM with sharpe between 0.5 and 1.0
    print('\n=== USA RAM with sharpe 0.5~1.0 ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, turnover, color
        FROM pipeline_alphas_bak 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND sharpe BETWEEN 0.5 AND 1.0
        ORDER BY sharpe DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0][:70] if row[0] else ''
        print(f'{expr:70s} | S={row[1]} F={row[2]} T={row[3]} | {row[4]}')

    # ALL USA RAM tested expressions (to check for duplicates)
    print('\n=== ALL tested USA RAM expressions (count) ===')
    r = conn.execute(text("""
        SELECT COUNT(DISTINCT expression_hash) 
        FROM pipeline_alphas_bak 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND is_tested = TRUE
    """))
    print(f'  Unique tested USA RAM: {r.scalar()}')

    # Recently tested (last 7 days)
    print('\n=== Recently tested USA RAM (last 7 days) ===')
    r = conn.execute(text("""
        SELECT alpha_expression, sharpe, fitness, backtested_at
        FROM pipeline_alphas_bak 
        WHERE alpha_expression LIKE '%group_neutralize%' 
        AND settings LIKE '%USA%'
        AND is_tested = TRUE
        AND backtested_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
        ORDER BY backtested_at DESC
        LIMIT 10
    """))
    for row in r:
        expr = row[0][:60] if row[0] else ''
        print(f'{expr:60s} | S={row[1]} F={row[2]} | {row[3]}')
