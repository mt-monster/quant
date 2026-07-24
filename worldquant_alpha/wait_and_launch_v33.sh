#!/bin/bash
cd C:/Users/MENGTAO/Desktop/E3/quant/worldquant_alpha
PY="C:/Users/MENGTAO/Desktop/E3/quant/.venv/Scripts/python"

echo "[$(date)] Waiting for API slots to clear..."
for i in $(seq 1 30); do
    # Test API availability
    result=$($PY -c "
import os, requests, time
from dotenv import load_dotenv
load_dotenv('.env')
s = requests.Session()
s.post('https://api.worldquantbrain.com/authentication', auth=(os.getenv('WQ_USERNAME'), os.getenv('WQ_PASSWORD')), timeout=30)
time.sleep(1)
data = {
    'type': 'REGULAR',
    'settings': {
        'instrumentType': 'EQUITY', 'delay': 1, 'decay': 4,
        'neutralization': 'SUBINDUSTRY', 'truncation': 0.08,
        'pasteurization': 'ON', 'unitHandling': 'VERIFY', 'nanHandling': 'ON',
        'language': 'FASTEXPR', 'visualization': False, 'testPeriod': 'P6Y',
        'region': 'KOR', 'universe': 'TOP600'
    },
    'regular': 'rank(close)'
}
r = s.post('https://api.worldquantbrain.com/simulations', json=data, timeout=30)
print(r.status_code)
" 2>/dev/null)

    if [ "$result" = "201" ]; then
        echo "[$(date)] API available! Launching V33..."
        $PY scan_v33_kor.py >> results/v33_console.log 2>&1
        echo "[$(date)] V33 finished."
        exit 0
    fi
    echo "[$(date)] Attempt $i: API still blocked ($result), waiting 60s..."
    sleep 60
done
echo "[$(date)] Timed out after 30 attempts. API still blocked."
