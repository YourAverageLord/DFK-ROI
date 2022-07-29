import json
import time
import aiohttp
import asyncio
import random
import sys
import textwrap

from web3 import Web3, datastructures
from web3.logs import DISCARD
from hexbytes import HexBytes

from core.globals import *
from core.quest.contracts import *
from core.dex import erc20


async def handle_errors(error):
    exception_type, exception_object, exception_traceback = sys.exc_info()
    filename = exception_traceback.tb_frame.f_code.co_filename
    line_number = exception_traceback.tb_lineno

    error_msg = textwrap.dedent(f"""```
    Exception occured:
        Type: {exception_type}
        Object: {exception_object}
        Where?: {filename}   Line num: {line_number}
    ```""")

    if exception_type == aiohttp.client_exceptions.ClientConnectorError:
        return f"Client connection error connecting to {exception_object.host}"
    elif exception_type == aiohttp.client_exceptions.ServerDisconnectedError:
        return f"Server connection error connecting to {exception_object.host}"
    else:
        return error_msg


async def get_all_user_tx(page_size, user_address, possible_rpcs, logger):

    # Get all user's transactions
    # Page count = # of tx user has made divided by pagination size (100)
    w3 = Web3(Web3.HTTPProvider(random.choice(possible_rpcs)))
    tx_count = w3.eth.getTransactionCount(user_address)
    total_pages = int(tx_count/page_size + 1)
    
    conn_limit = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=conn_limit) as session:
        tasks = []
        for page_num in range(total_pages):
            tasks.append(get_Tx_History(user_address, possible_rpcs, session, page_size, page_num, logger))
        
        paginated_tx = await asyncio.gather(*tasks)
    
    return paginated_tx


async def get_Tx_History(user_address, possible_rpcs, session, page_size, page_num, logger):
    fetch_start = time.perf_counter()

    encoded_data = json.dumps(
        {
            "jsonrpc":"2.0",
            "method":"hmyv2_getTransactionsHistory",
            "id":1,
            "params":[
                {
                    "fullTx":True,
                    "txType":"SENT",
                    "order":"DESC",
                    "address":user_address,
                    "pageIndex":page_num,
                    "pageSize":page_size
                }
            ]
        }
    ).encode('utf-8')

    transactions = False
    while not transactions:
        try:
            rpc = random.choice(possible_rpcs)

            async with session.post(rpc, data=encoded_data, headers={'Content-Type': 'application/json'}) as r:
                if r.status != 200:
                    asyncio.sleep(5)
                    continue

                results = await r.json()
                
                if results.get("error"):
                    raise Exception(results["error"])
                    
                if results.get('result', {}).get("transactions"):
                    if all(results["result"]["transactions"]):
                        transactions = results["result"]["transactions"]
                    else:
                        asyncio.sleep(5)
                        continue
        
        except Exception as e:
            logger.warn(await handle_errors(e))
            asyncio.sleep(5)
    
    # logger.info(f"Fetched {page_size} tx via {rpc} took {time.perf_counter() - start}")
    return transactions


async def sort_Transactions(sort, contracts, all_tx_list, possible_rpcs):
    w3 = Web3(Web3.HTTPProvider(random.choice(possible_rpcs)))

    if sort == "questComplete":

        tasks = []
        for tx in all_tx_list:  # each tx_list has 100 tx
            tasks.append(extract_questComplete(tx, contracts))
                                
        questComplete_txs = (await asyncio.gather(*tasks))
        questComplete_txs = list(filter(None, questComplete_txs))

        return questComplete_txs


async def extract_questComplete(tx, quest_contracts):
    contract_one = tx.get("to", "").lower()
    quest_contract = quest_contracts.get(contract_one, {}).get("contract")
    
    if quest_contract:
        decoded_tx = quest_contract.decode_function_input(tx["input"])
        if decoded_tx[0].fn_name == "completeQuest":    
            return tx


async def fetch_raw_tx_receipts(transactions, possible_rpcs, logger):
    
    # Fetch all tx receipts    
    conn_limit = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=conn_limit) as session:
        tasks = []
        for tx in transactions:
            tasks.append(get_tx_receipt_http(possible_rpcs, session, tx["hash"], logger))

        raw_tx_receipts = (await asyncio.gather(*tasks))
    
    return raw_tx_receipts


async def get_tx_receipt_http(possible_rpcs, session, tx_hash, logger):
    start = time.perf_counter()
    
    encoded_data = json.dumps(
        {
           "jsonrpc":"2.0","method": 
           "eth_getTransactionReceipt", 
           "params": [tx_hash], 
           "id": 1
        }
    ).encode('utf-8')

    good_results = False
    while not good_results:
        try:
            rpc = random.choice(possible_rpcs)

            async with session.post(rpc, data=encoded_data, headers={'Content-Type': 'application/json'}) as r:
                if r.status != 200:
                    asyncio.sleep(3)
                    continue

                results = await r.json()
                
                if results.get("error"):
                    raise Exception(results["error"])

                if results.get("result"):
                    if all(results["result"]):
                        good_results = results["result"]
                    else:
                        asyncio.sleep(5)
                        continue

        except Exception as e:
            logger.warn(await handle_errors(e))
            asyncio.sleep(3)
    
    # logger.info(f"Fetched tx receipt via {rpc} took {time.perf_counter() - start}")
    return good_results


async def raw_2_web3_receipt(transactions):
    
    tasks = []
    for tx in transactions:        
        tasks.append(convert_web3_receipt(tx))
        
    web3_receipts = (await asyncio.gather(*tasks))

    return web3_receipts


async def convert_web3_receipt(tx):
    tx["blockHash"] = HexBytes(tx["blockHash"])
    tx["blockNumber"] = Web3.toInt(HexBytes(tx["blockNumber"]))
    tx["cumulativeGasUsed"] = Web3.toInt(HexBytes(tx["cumulativeGasUsed"]))
    tx["from"] = Web3.toChecksumAddress(tx["from"])
    tx["gasUsed"] = Web3.toInt(HexBytes(tx["gasUsed"]))
    tx["logsBloom"] = HexBytes(tx["logsBloom"])
    tx["status"] = Web3.toInt(HexBytes(tx["status"]))
    tx["to"] = Web3.toChecksumAddress(tx["to"])
    tx["transactionHash"] = HexBytes(tx["transactionHash"])
    tx["transactionIndex"] = Web3.toInt(HexBytes(tx["transactionIndex"]))

    # need to match up logs for each
    # l = dict(tx["logs"][0])
    for l in  tx["logs"]:
        new_log = {}
        new_log["address"] = Web3.toChecksumAddress(l["address"])
        new_log["blockHash"] = HexBytes(l["blockHash"])
        new_log["blockNumber"] = Web3.toInt(HexBytes(l["blockNumber"]))
        new_log["data"] = l["data"]
        new_log["logIndex"] = Web3.toInt(HexBytes(l["logIndex"]))
        new_log["removed"] = l["removed"]
        new_log["topics"] = [HexBytes(x) for x in l["topics"]]
        new_log["transactionHash"] = HexBytes(l["transactionHash"])
        new_log["transactionIndex"] = Web3.toInt(HexBytes(l["transactionIndex"]))
        
        tx["logs"][tx["logs"].index(l)] = datastructures.AttributeDict(new_log)
 
    return tx


async def process_quest_receipts(tx_receipts, quest_contracts_hex, realm):
    tasks = []
    total_quest_rewards = {}

    for rcpt in tx_receipts:  # each tx_list has 100 tx
        contract_hex = rcpt.get("to", "").lower()
        tasks.append(parse_quest_receipt(quest_contracts_hex.get(contract_hex), rcpt, realm))
    
    quest_results = (await asyncio.gather(*tasks))

    for result in quest_results:
        for hero_id, values in result.items():
            
            if hero_id not in total_quest_rewards:
                total_quest_rewards[hero_id] = {'rewards': {}, 'xpEarned': 0.0, 'skillUp': 0.0, "total_in_jewel": 0.0}

            for item, qty in values["rewards"].items():
                if item not in total_quest_rewards[hero_id]["rewards"]:
                    total_quest_rewards[hero_id]["rewards"][item] = qty
                else:
                    total_quest_rewards[hero_id]["rewards"][item] += qty

            total_quest_rewards[hero_id]["xpEarned"] += values["xpEarned"]
            total_quest_rewards[hero_id]["skillUp"] += values["skillUp"]

    return total_quest_rewards


async def parse_quest_receipt(contract, tx_receipt, realm):
    V1_CONTRACT_ADDRESS = V1_SERENDALE_CONTRACT_HEX
    
    if realm == "serendale":
        V2_CONTRACT_ADDRESS = V2_SERENDALE_CONTRACT_HEX
    else:
        V2_CONTRACT_ADDRESS = V2_CRYSTALVALE_CONTRACT_HEX

    quest_rewards = {}
    
    if not contract:
        return quest_rewards

    is_quest_v2 = (contract.address.lower() == V2_CONTRACT_ADDRESS)
    
    if is_quest_v2:
        amount_key, reward_key = 'amount', 'reward'
        quest_reward = contract.events.RewardMinted().processReceipt(tx_receipt, errors=DISCARD)
    else:
        amount_key, reward_key = 'itemQuantity', 'rewardItem'
        quest_reward = contract.events.QuestReward().processReceipt(tx_receipt, errors=DISCARD)

    quest_xps = contract.events.QuestXP().processReceipt(tx_receipt, errors=DISCARD)
    skill_ups = contract.events.QuestSkillUp().processReceipt(tx_receipt, errors=DISCARD)
    
    rewards = quest_reward
    xps = quest_xps
    skill_ups = skill_ups

    for rew in rewards:
        hero_id = rew['args']['heroId']
        item = erc20.address2item(rew['args'][reward_key], realm)
        
        if item[1] == "JEWEL":
            qty = rew['args'][amount_key] / 1e18
        elif item[1] == "DFKGOLD":
            qty = rew['args'][amount_key] / 1e3
        else:
            qty = rew['args'][amount_key]

        if not hero_id in quest_rewards:
            quest_rewards[hero_id] = {
                "rewards": {},
                "xpEarned": 0.0,
                "skillUp": 0.0
            }

        if not item[1] in quest_rewards[hero_id]["rewards"]:
            quest_rewards[hero_id]["rewards"][item[1]] = 0

        quest_rewards[hero_id]["rewards"][item[1]] += qty

    for xp in xps:
        hero_id = xp['args']['heroId']
        xp_earned = xp['args']['xpEarned']

        if not hero_id in quest_rewards:
            quest_rewards[hero_id] = {
                "rewards": {},
                "xpEarned": 0.0,
                "skillUp": 0.0
            }

        quest_rewards[hero_id]["xpEarned"] += xp_earned
        
    for su in skill_ups:
        hero_id = su['args']['heroId']
        su_earned = su['args']['skillUp']

        if not hero_id in quest_rewards:
            quest_rewards[hero_id] = {
                "rewards": {},
                "xpEarned": 0.0,
                "skillUp": 0.0
            }

        quest_rewards[hero_id]["skillUp"] += su_earned

    return quest_rewards