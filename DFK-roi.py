import os
import argparse
import asyncio
import textwrap
import time
import random
import json
import requests

from web3 import Web3
from datetime import datetime
from datetime import timedelta

import core.dex.erc20 as tokens
import core.dex.item_pools as item_pools

import core.dex.uniswap_v2_pair as pair
import core.dex.uniswap_v2_router as trader

from core.globals import *
from core.funcs.funcs import load_config, set_up_logger, handle_errors
from core.funcs.async_funcs import get_all_user_tx, sort_Transactions, fetch_raw_tx_receipts, raw_2_web3_receipt, process_quest_receipts
from core.API.funcs import get_hero_rental_history


from core.quest.contracts import QUEST_V1_CONTRACT_ADDRESS, QUEST_V2_CONTRACT_ADDRESS 
from core.quest.abis import QUEST_V1_ABI, QUEST_V2_ABI


parser = argparse.ArgumentParser(
    description="DFK ROI!",
    prog='python3 DFK-roi.py',
    formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument(
    '-a', '--address', action="store", default=None, dest='address', 
    required=True,
    help="Specify the 0x address you want to get an ROI report for.")
parser.add_argument(
    '--rentals', action="store_true", default=None, dest='rentals', 
    help="Query tavern rental profits")
parser.add_argument(
    '--quest-rewards', action="store", default=None, dest='quest_rewards', 
    choices=["24h", "lifetime"], help="Query quest reward profits")
parser.add_argument(
    '--file', action="store", default=None, dest='file', 
    help="Read from file instead of fetching from the blockchain")
parser.add_argument(
    '-cr', '--custom-rpc', action="store_true", default=None, dest='custom_rpc', 
    help="Use custom RPCs defined in config.yaml")
parser.add_argument(
    '--test', action="store_true", default=None, dest='test', 
    help="Run the testing code")
	
# init the pargs variable with parser args
pargs = parser.parse_args()

# Set up the logger
logger = set_up_logger("ROI", False)

CONFIG = load_config()
webhook = CONFIG.get("discord").get("webhooks").get("roi report")
if "https://" not in webhook:
    logger.critical("Need webhook URL! Plz configure in core/config.yaml. See README for info")
    exit()

possible_rpcs = [
    "https://api.harmony.one",
    "https://a.api.s0.t.hmny.io",
    "https://api.s0.t.hmny.io",
    ]

custom_rpcs = CONFIG.get('custom rpcs', [])

rpc_server = random.choice(possible_rpcs)
w3 = Web3(Web3.HTTPProvider(rpc_server))
user_address = pargs.address
# latest_block_num  = w3.eth.block_number

main_start = time.perf_counter()
try:
    
    # Gen0 rentals ROI
    if pargs.rentals:
        total, msg = 0.00, ""
        rental_data = get_hero_rental_history(user_address)
        for hero, data in rental_data.items():
            total += data["total"]
            msg += textwrap.dedent(
                f"""
                Hero: {hero}
                    Total rentals: {len(data["rentals"])}
                    Total jewel: {data["total"]}
                    Avg price per rental: {data["total"] / len(data["rentals"])}
                """)
        
        msg = f"**Rental Report**\n```{msg}```\nTotal jewel: {total}"
        logger.info(msg)
    

    # Quest rewards ROI
    if pargs.quest_rewards:
        if pargs.file:
            # read from saved quest rewards file
            with open(pargs.file, "r") as inf:
                quest_rewards = json.load(inf)
        else:
            quest_contracts_one = {
                "one12yqt6vdcygm3zz9q7c7uldjefwv3n6h5trltq4": {
                    "hex": QUEST_V1_CONTRACT_ADDRESS,
                    "contract": w3.eth.contract(
                        w3.toChecksumAddress(QUEST_V1_CONTRACT_ADDRESS), abi=QUEST_V1_ABI)
                    },
                "one142dz388q2e0y6e2gucayg8nupp8xk5hk62auhh": {
                    "hex": QUEST_V2_CONTRACT_ADDRESS,
                    "contract": w3.eth.contract(
                        w3.toChecksumAddress(QUEST_V2_CONTRACT_ADDRESS), abi=QUEST_V2_ABI)
                    }
                }

            quest_contracts_hex = {
                QUEST_V1_CONTRACT_ADDRESS: w3.eth.contract(
                    w3.toChecksumAddress(QUEST_V1_CONTRACT_ADDRESS), abi=QUEST_V1_ABI),
                QUEST_V2_CONTRACT_ADDRESS: w3.eth.contract(
                    w3.toChecksumAddress(QUEST_V2_CONTRACT_ADDRESS), abi=QUEST_V2_ABI)
                }

            # get all user's TX
            start = time.perf_counter()
            logger.info(f"Getting all TX...")
            page_size = 100
            paginated_tx = asyncio.run(get_all_user_tx(page_size, user_address, possible_rpcs, logger))
            all_tx_list = [x for tx_list in paginated_tx for x in tx_list]
            logger.info(f"Fetched {len(paginated_tx) * page_size} TX in {time.perf_counter() - start} secs")

            # Extract all the ones that are questComplete
            start = time.perf_counter()
            logger.info(f"Extracting all questComplete Txs...")
            questComplete_txs = asyncio.run(sort_Transactions("questComplete", quest_contracts_one, all_tx_list, possible_rpcs))
            logger.info(f"Extracted {len(questComplete_txs)} questComplete TX in {time.perf_counter() - start} secs")

            # get yesterday's quest rewards, or lifetime?
            if pargs.quest_rewards == "24h":
                today = datetime.today()
                yesterday = today - timedelta(days = 1)
                yesterday_tx = []
                for i in questComplete_txs:
                    tx_date = datetime.fromtimestamp(i["timestamp"])
                    if tx_date < today and tx_date >= yesterday:
                        # print(tx_date)
                        yesterday_tx.append(i)
                
                rcpts_2_fetch = yesterday_tx
            else:
                rcpts_2_fetch = questComplete_txs

            # Fetch all the raw Tx receipts
            start = time.perf_counter()
            logger.info(f"Fetching TX receipts...")
            raw_tx_receipts = asyncio.run(fetch_raw_tx_receipts(rcpts_2_fetch, possible_rpcs, logger))
            logger.info(f"Fetched {len(raw_tx_receipts)} tx receipts from {pargs.quest_rewards} in {time.perf_counter() - start} secs")

            # Convert all the raw Tx receipts
            start = time.perf_counter()
            logger.info(f"Converting TX receipts...")
            web3_tx_receipts = asyncio.run(raw_2_web3_receipt(raw_tx_receipts))
            logger.info(f"Converted {len(web3_tx_receipts)} raw tx receipts to web3 receipts in {time.perf_counter() - start} secs")
            
            # Process quest receipts
            start = time.perf_counter()
            logger.info(f"Processing quest Receipts...")
            quest_rewards = asyncio.run(process_quest_receipts(web3_tx_receipts, quest_contracts_hex))
            logger.info(f"Processed rewards for {len(quest_rewards)} heroes in {time.perf_counter() - start} secs")

            quest_rewards_outfile = f"{OUT_DIR}/{pargs.quest_rewards}_quest_rewards.json"
            with open(quest_rewards_outfile, "w") as outf:
                json.dump(quest_rewards, outf)
            logger.info(f"Saved quest rewards to {quest_rewards_outfile}")
        
        # Get prices for items in JEWEL via WJEWEL/USDC
        jewel_price = 0
        url = "https://api.dexscreener.com/latest/dex/pairs/avalanchedfk/0xcf329b34049033de26e4449aebcb41f1992724d3"
        while jewel_price == 0:
            try:
                resp = requests.get(url)
                
                if resp.status_code != 200:
                    continue

                jewel_price = float(resp.json()["pair"]["priceNative"])
                logger.info(f"Fetched JEWEL price: {jewel_price} USD")

            except Exception as e:
                error_msg = handle_errors(e)
                logger.error(f"{error_msg}")
            
        success = False
        while not success:
            try:
                for x, y in item_pools.ITEM_POOLS.items():
                    url = f'https://api.dexscreener.com/latest/dex/pairs/{y["chain"]}/{y["pairAddress"]}'
                    resp = requests.get(url)
                    
                    if resp.status_code != 200:
                        continue
                    
                    if resp.json()["pair"]["quoteToken"]["symbol"] == "JEWEL":
                        item_pools.ITEM_POOLS[x]["item_price_in_jewel"] = float(resp.json()["pair"]["priceNative"])
                    else:
                        item_pools.ITEM_POOLS[x]["item_price_in_jewel"] = float(resp.json()["pair"]["priceUsd"]) / jewel_price

                    logger.info(f'Fetched {x} price: {item_pools.ITEM_POOLS[x]["item_price_in_jewel"]} jewel')
                
                success = True

            except Exception as e:
                error_msg = handle_errors(e)
                logger.error(f"{error_msg}")
        
        # After quest_rewards is fetched, total it up
        total_jewel = 0
        total_gold = 0
        total_shvas_runes = 0
        for hero, rewards in quest_rewards.items():
            for item, amount in rewards["rewards"].items():
                if item != "JEWEL":
                    if item == "NOTHING":
                        continue
                    for x, y in item_pools.ITEM_POOLS.items():
                        if item in y["items"] and "JEWEL" in y["items"]:
                            quest_rewards[hero]["total_in_jewel"] += amount * y["item_price_in_jewel"]
                else:
                    quest_rewards[hero]["total_in_jewel"] += amount

            total_jewel += rewards["total_in_jewel"]
            total_gold += rewards["rewards"].get("DFKGOLD", 0)
            total_shvas_runes += rewards["rewards"].get("DFKSHVAS", 0)
        
        msg = textwrap.dedent(f"Totals:\n\t\
            Total of all items in JEWEL: {total_jewel}\n\t\
            Total GOLD recieved: {total_gold}\n\t\
            Total SHVAS RUNES recieved: {total_shvas_runes}")

        logger.info(msg)
        print()


    if pargs.test:
        # dex screener API jewel/bloater
        # https://api.dexscreener.com/latest/dex/pairs/harmony/0xc41235202daa55064d69981b6de4b7947868bb45
        print()
        
        # token_address = tokens.symbol2address('JEWEL')
        # name = tokens.name(token_address, rpc_server)
        # symbol = tokens.symbol(token_address, rpc_server)
        # decimal = tokens.decimals(token_address, rpc_server)
        # balance = tokens.balance_of(user_address, token_address, rpc_server)
        # balance = tokens.wei2eth(w3, balance)

        # #JEWEL/stam pot pair
        # JEWEL_DFKRGWD_addy = "0x2e7276584897a099d07b118fad51ad8c169f01ee"
        # JEWEL_DFKRGWD_Pair = pair.UniswapV2Pair(JEWEL_DFKRGWD_addy, rpc_server, logger)
        # pair_balance = JEWEL_DFKRGWD_Pair.balance_of(user_address)
        # f"{0:.10f}".format(pair_balance)
        # # Expected amount of jewel when providing x of stampot
        # amount_in_jewel = JEWEL_DFKRGWD_Pair.expected_amount1(1)
        print()

except Exception as e:
    error_msg = handle_errors(e)
    logger.error(error_msg)

logger.info(f"Processed everything in {time.perf_counter() - main_start} secs")
print()