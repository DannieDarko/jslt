import json
import sys
from copy import deepcopy
from datetime import timedelta
from jslt import JSLT
from pathlib import Path
from time import time

CWD = Path(__file__).parent

def test_transform():
    with open(CWD / 'jslt.json', 'r') as f:
        jsl_proc=JSLT(json.load(f))
    with open(CWD / 'order.json', 'r') as f:
        transformed=jsl_proc.transform(json.load(f))
    print(json.dumps(transformed, indent=2))

def benchmark_transform(iterations: int=10_000):
    start_time=time()
    print('Load JSLT...')
    with open(CWD / 'jslt_orders.json', 'r') as f:
        jsl_proc=JSLT(json.load(f))
    print(f'    {timedelta(seconds=time()-start_time)}')
    print('Load orders')
    now=time()
    data=[]
    with open(CWD / 'order.json', 'r') as f:
        order=json.load(f)
        print(f'    {timedelta(seconds=time()-now)}')
        print('Generate orders')
        for i in range(1, iterations+1):
            new_order=deepcopy(order)
            new_order['id']=i
            new_order['documentNumber']=f"{new_order['documentNumber'][:-6]}{i:06}"
            new_order['customer']['id']=i
            new_order['customer']['number']=f"{new_order['customer']['number'][:-6]}{i:05}"
            new_order['externalOrderId']=f"{new_order['externalOrderId'][:-7]}{i:07}"
            new_order['externalOrderNumber']=f"{new_order['externalOrderId'][:-7]}{i:07}"
            data.append(new_order)
    print(f'    {timedelta(seconds=time()-now)}')
    print('Transform')
    now=time()
    transformed=jsl_proc.transform(data)
    print(f'    {timedelta(seconds=time()-now)}')
    print(f'Total {len(transformed)} in {timedelta(seconds=time()-start_time)}')

if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1] == 'benchmark':
        benchmark_transform()
    else:
        test_transform()