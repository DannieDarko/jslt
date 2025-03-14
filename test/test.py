import json
from jslt import JSLT

with open('jslt.json', 'r') as f:
    jsl_proc=JSLT(json.load(f))
with open('request.json', 'r') as f:
    transformed=jsl_proc.transform(json.load(f))
print(json.dumps(transformed, indent=2))
