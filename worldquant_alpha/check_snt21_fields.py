from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import re, os

load_dotenv('.env')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'worldquant_alpha')
DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

fields = set()
with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT DISTINCT alpha_expression
        FROM pipeline_bak_0417 
        WHERE settings LIKE '%USA%'
        AND alpha_expression LIKE '%snt21%'
        AND is_tested = TRUE
    """))
    for row in r:
        expr = row[0] if row[0] else ''
        matches = re.findall(r'snt21_[a-zA-Z0-9_]+', expr)
        for m in matches:
            fields.add(m)

print('snt21 fields used in USA:')
for f in sorted(fields):
    print(f'  {f}')
