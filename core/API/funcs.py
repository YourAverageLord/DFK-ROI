import requests
from time import sleep

from core.funcs.funcs import InvalidStatusCode, wei2ether


def get_hero_sale_history(hero_id):
    sale_history = {}
    url = "https://us-central1-defi-kingdoms-api.cloudfunctions.net:443/query_saleauctions"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:100.0) Gecko/20100101 Firefox/100.0", "Accept": "*/*", "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate", "Referer": "https://beta.defikingdoms.com/", "Content-Type": "application/json", "Origin": "https://beta.defikingdoms.com", "Dnt": "1", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site", "Te": "trailers"}
    json={
        "limit": 100, "offset": 0, "order": 0, 
        "params": [
            {"field": "open", "operator": "=", "value": False}, 
            {"field": "tokenid", "operator": "=", "value": hero_id}
            ]
    }

    resp = requests.post(url, headers=headers, json=json)
    
    if resp.status_code != 200:
        raise InvalidStatusCode(str(resp.status_code))

    sale_history['history'] = resp.json()
    
    latest_auct_id = 0
    for i in resp.json():
        if int(i['id']) > latest_auct_id:
            latest_auct_id = int(i['id'])

    for i in resp.json():
        if int(i['id']) == latest_auct_id:
            sale_history['last sale price'] = wei2ether(i['endingprice'])
            sale_history['last winner'] = i['winner_name']

    return sale_history


def get_hero_rental_history(user_address):
    rentals = True
    full_data = {}
    offset = 0
    orderby = "endedat"
    orderdir = "desc"
    url = "https://us-central1-defi-kingdoms-api.cloudfunctions.net:443/query_assistauctions"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:100.0) Gecko/20100101 Firefox/100.0", "Accept": "*/*", "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate", "Referer": "https://beta.defikingdoms.com/", "Content-Type": "application/json", "Origin": "https://beta.defikingdoms.com", "Dnt": "1", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site", "Te": "trailers"}
    
    while rentals:
        json={
            "limit":100,
            "params":[
                {"field":"open","operator":"=","value":False},
                {"field":"seller","operator":"=","value":user_address},
                
                ],
                "offset":offset,
                "order":{
                    "orderBy":orderby,
                    "orderDir":orderdir}
        }

        resp = requests.post(url, headers=headers, json=json)
        
        if resp.status_code != 200:
            raise InvalidStatusCode(str(resp.status_code))
        
        rentals = resp.json()
        for rental in rentals:
            if rental["winner"]:
                hero_id = rental["tokenid"]

                if not hero_id in full_data:
                    full_data[hero_id] = {"rentals":[], "total": 0.00}

                rental["rental price"] = wei2ether(int(rental["purchaseprice"]))
                full_data[hero_id]["total"] += rental["rental price"]
                full_data[hero_id]["rentals"].append(rental)                

        offset += 100
        sleep(.5)

    return full_data