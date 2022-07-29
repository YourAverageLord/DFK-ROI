import os
import argparse
import asyncio
import textwrap
import time
import random
import json

from web3 import Web3
from datetime import datetime
from datetime import timedelta

import core.dex.utils.utils as dex_utils

from core.globals import *
from core.funcs.funcs import *
from core.funcs.async_funcs import get_all_user_tx, sort_Transactions, fetch_raw_tx_receipts, raw_2_web3_receipt, process_quest_receipts
from core.API.funcs import get_hero_rental_history

from core.quest.contracts import *
from core.quest.abis import *


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
    '--quest-rewards', action="store", default="24h", dest='quest_rewards', 
    choices=["24h", "lifetime"], help="Query quest reward profits")
parser.add_argument(
    '--file', action="store_true", default=False, dest='file', 
    help="Read from stored file instead of fetching from the blockchain")
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
webhook = CONFIG.get("discord", {}).get("webhooks", {}).get("roi report")
# if "https://" not in webhook:
#     logger.critical("Need webhook URL! Plz configure in core/config.yaml. See README for info")
#     exit()

possible_rpcs = [
    "https://api.harmony.one",
    "https://a.api.s0.t.hmny.io",
    "https://api.s0.t.hmny.io",
    ]

if pargs.custom_rpc:
    possible_rpcs = CONFIG.get('custom rpcs', [])

rpc_server = random.choice(possible_rpcs)
w3 = Web3(Web3.HTTPProvider(rpc_server))
user_address = pargs.address
# latest_block_num  = w3.eth.block_number

main_start = time.perf_counter()
try:
    create_folder_structure()

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
        exit()
    

    # Quest rewards ROI
    if pargs.quest_rewards:
        quest_rewards_outfile = f"{OUT_DIR}/{pargs.quest_rewards}_quest_rewards.json"
        
        if pargs.file:
            if not os.path.exists(quest_rewards_outfile):
                logger.critical(f"Couldn't find {quest_rewards_outfile}!")
                exit()

            # read from saved quest rewards file
            with open(quest_rewards_outfile, "r") as inf:
                quest_rewards = json.load(inf)
        else:
            realm = "serendale"
            V1_CONTRACT_ADDRESS = V1_SERENDALE_CONTRACT_HEX

            if realm == "serendale":
                V2_CONTRACT_ADDRESS = V2_SERENDALE_CONTRACT_HEX
            else:
                V2_CONTRACT_ADDRESS = V2_CRYSTALVALE_CONTRACT_HEX

            quest_contracts_one = {
                V1_SERENDALE_CONTRACT_ONE: {
                    "hex": V1_CONTRACT_ADDRESS,
                    "contract": w3.eth.contract(w3.toChecksumAddress(
                        V1_CONTRACT_ADDRESS), abi=QUEST_V1_ABI)
                    },
                V2_SERENDALE_CONTRACT_ONE: {
                    "hex": V2_CONTRACT_ADDRESS,
                    "contract": w3.eth.contract(w3.toChecksumAddress(
                        V2_CONTRACT_ADDRESS), abi=QUEST_V2_ABI)
                    }
                }

            quest_contracts_hex = {
                V1_CONTRACT_ADDRESS: w3.eth.contract(
                    w3.toChecksumAddress(V1_CONTRACT_ADDRESS), abi=QUEST_V1_ABI),
                V2_CONTRACT_ADDRESS: w3.eth.contract(
                    w3.toChecksumAddress(V2_CONTRACT_ADDRESS), abi=QUEST_V2_ABI)
                }

            # get all user's TX
            start = time.perf_counter()
            logger.info(f"Getting all TX...")
            page_size = 100
            paginated_tx = asyncio.run(get_all_user_tx(page_size, user_address, possible_rpcs, logger))
            all_tx_list = [tx for tx_list in paginated_tx for tx in tx_list]
            logger.info(f"Fetched {len(all_tx_list)} TX in {time.perf_counter() - start} secs")

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
            quest_rewards = asyncio.run(process_quest_receipts(web3_tx_receipts, quest_contracts_hex, realm))
            logger.info(f"Processed rewards for {len(quest_rewards)} heroes in {time.perf_counter() - start} secs")

        # for each hero, get quest item prices in jewel for the amount
        logger.info("Getting all item prices in jewel. This may take a minute or 3...")
        item_prices = dex_utils.get_item_prices(user_address, realm, possible_rpcs, logger)

        all_total_in_jewel = 0
        for hero_id, rewards in quest_rewards.items():
            for rew, amount in rewards["rewards"].items():
                if rew == "JEWEL":
                    quest_rewards[hero_id]["total_in_jewel"] += amount
                else:
                    quest_rewards[hero_id]["total_in_jewel"] += float(amount) * float(item_prices.get(rew, 0.0))

            all_total_in_jewel += quest_rewards[hero_id]["total_in_jewel"]

        # store data to JSON file
        with open(quest_rewards_outfile, "w") as outf:
            json.dump(quest_rewards, outf)
        logger.info(f"Saved quest rewards to {quest_rewards_outfile}")
        
        print(f"Total price of all items in JEWEL for {pargs.quest_rewards} time period: {all_total_in_jewel}")
        exit()

    if pargs.test:
        print("test")
        exit()
        
        
except Exception as e:
    error_msg = handle_errors(e)
    logger.error(error_msg)

logger.info(f"Processed everything in {time.perf_counter() - main_start} secs")
