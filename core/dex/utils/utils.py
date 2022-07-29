import random
import sys

from web3 import Web3
from time import sleep

from .. import erc20
from .. import uniswap_v2_factory as market_place_factory
from .. import uniswap_v2_pair as pool
from .. import uniswap_v2_router as router


def swap_expected_amount1(reserve0, reserve1, amount0_wei=1):
    p = reserve0 / reserve1
    amount1_wei = amount0_wei / p
    p2 = (reserve0 + amount0_wei) / (reserve1 - amount1_wei)
    return (amount1_wei + amount0_wei / p2) / 2


def human_readable_pool_info(pool_info):
    if pool_info is None:
        return None

    human_readable = {}
    human_readable['address'] = pool_info[0]
    human_readable['allocPoint'] = pool_info[1]
    human_readable['lastRewardBlock'] = pool_info[2]
    human_readable['accGovTokenPerShare'] = pool_info[3]

    return human_readable


def human_readable_user_info(user_info):
    if user_info is None:
        return None

    human_readable = {}
    human_readable['amount'] = user_info[0]
    human_readable['rewardDebt'] = user_info[1]
    human_readable['rewardDebtAtBlock'] = user_info[2]
    human_readable['lastWithdrawBlock'] = user_info[3]
    human_readable['firstDepositBlock'] = user_info[4]
    human_readable['blockdelta'] = user_info[5]
    human_readable['lastDepositBlock'] = user_info[6]

    return human_readable


def get_item_prices(realm, possible_rpcs, logger):
    ''' Get item prices non-async'''

    item_prices = {}
    realm_items = erc20.get_realm_item_list(realm)
    token_address_1 = erc20.symbol2address('JEWEL', realm)

    for item in realm_items:
        if item[1] != "JEWEL" and item[1] != "NOTHING":
            
            price_in_jewel, retries = None, 0
            while not price_in_jewel:
                try:
                    if retries > 3:
                        logger.error(f"Issue with retrieving price for {item[1]}")
                        break

                    rpc_server = random.choice(possible_rpcs)
                    w3 = Web3(Web3.HTTPProvider(rpc_server))

                    token_address_2 = erc20.symbol2address(item[1], realm)
                    pair_address = market_place_factory.get_pair(token_address_1, token_address_2, rpc_server)
                    
                    Pair = pool.UniswapV2Pair(pair_address, rpc_server, logger)
                    reserve0, reserve1, blockTimestampLast =  Pair.reserves()

                    if Pair.token_0() == token_address_1:
                        price_in_jewel = erc20.wei2eth(w3, router.get_amount_out(1, reserve1, reserve0, rpc_server))
                    
                    elif Pair.token_1() == token_address_1:
                        price_in_jewel = erc20.wei2eth(w3, router.get_amount_out(1, reserve0, reserve1, rpc_server))

                    item_prices[item[1]] = price_in_jewel
                    # logger.debug(f"{item[1]}: {item_prices[item[1]]}")
                    sleep(1)
                
                except Exception as e:
                    error_msg = str(e)
                    retries += 1

    return item_prices    