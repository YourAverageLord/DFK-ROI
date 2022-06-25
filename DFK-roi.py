import os
import argparse
import asyncio
import textwrap
import time
import random
import json

from web3 import Web3

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
    '--quest-rewards', action="store_true", default=None, dest='quest_rewards', 
    help="Query quest reward profits")
	
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

w3 = Web3(Web3.HTTPProvider(random.choice(possible_rpcs)))
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

        # Fetch all the raw Tx receipts
        start = time.perf_counter()
        logger.info(f"Fetching TX receipts...")
        raw_tx_receipts = asyncio.run(fetch_raw_tx_receipts(questComplete_txs, possible_rpcs, logger))
        logger.info(f"Fetched {len(raw_tx_receipts)} tx receipts in {time.perf_counter() - start} secs")

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

        quest_rewards_outfile = f"{OUT_DIR}/quest_rewards.json"
        with open(quest_rewards_outfile, "w") as outf:
            json.dump(quest_rewards, outf)
        logger.info(f"Saved quest rewards to {quest_rewards_outfile}")

except Exception as e:
    error_msg = handle_errors(e)
    logger.error(error_msg)

logger.info(f"Processed everything in {time.perf_counter() - main_start} secs")