import sys, os, json
import pandas as pd

sys.path.insert(0, f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")

from core.globals import *
from core.dex import erc20

input_csv = f"{SCRIPT_DIR}/scripts/Copy of FaultyPoker's DFK Unincentivized Pool Returns - UnincentivizedPools.csv"
df = pd.read_csv(input_csv)

item_pools = {}

# get the pool pairs into a dict
for i, pool in enumerate(df["Pool"]):
    item_pools[pool] = {"pairAddress": df["pairAddress"][i], "chain": df["chain"][i], "items": []}

# get the token names into the dict
for j in erc20.ITEMS:
    for s in item_pools:
        pool_items = [x.lower().strip() for x in s.split('<>')]
        if j[2].lower() in pool_items:
            item_pools[s]["items"].append(j[1])


item_pools_pretty = json.dumps(item_pools, indent=4, sort_keys=True)

with open(f"{SCRIPT_DIR}/core/dex/item_pools.py", "w") as outfile:
    outfile.write(f'ITEM_POOLS = {item_pools_pretty}')
