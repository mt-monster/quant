from worldquant_alpha.database import get_session
from sqlalchemy import text

session = get_session()

# Check all tables
result = session.execute(text('SHOW TABLES'))
tables = [r[0] for r in result]
print('All tables:', tables)
print()

# Check alphas in each table
for table in tables:
    if 'alpha' in table.lower():
        try:
            result = session.execute(text(f'SELECT COUNT(*) FROM {table}'))
            count = result.scalar()
            print(f'{table}: {count} records')
        except Exception as e:
            print(f'{table}: Error - {e}')

print()
# Check if there's any alpha with anl14
result = session.execute(text("""
    SELECT COUNT(*) FROM alpha_results
    WHERE raw_result LIKE '%anl14%'
"""))
count = result.scalar()
print(f'alpha_results with anl14: {count}')

session.close()
