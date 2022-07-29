import sys
import textwrap
import requests
import warnings
import yaml
import logging
import debugpy

from datetime import datetime

from core.globals import *

warnings.filterwarnings("ignore")


# Custom exceptions
class InvalidStatusCode(Exception):
    pass


def block_explorer_link(txid):
    return 'https://explorer.harmony.one/tx/' + str(txid)


def wei2ether(wei):
    return float(wei) / 1000000000000000000


def ether2wei(ether):
    return int(ether * 1000000000000000000)
    

def load_config():
    with open(f"{SCRIPT_DIR}/core/config.yaml") as c:
        CONFIG = yaml.load(c, Loader=yaml.FullLoader)
    
    return CONFIG


def create_folder_structure():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)


def wait_for_debugger(webhook):
    """ This function serves as a hook to allow you to attach with VSCode. """

    debug, port = False, 5678
    while not debug:
        try:
            debugpy.listen(port)
            debug = True
        except:
            port +=1
        
    msg = f"Waiting for debugger attach: {port}"
    if webhook:
        send_notif(webhook, msg, None)
    else:
        print(msg)
    debugpy.wait_for_client()
    debugpy.breakpoint()


def set_up_logger(logger_name, to_file):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    logDir = f'{SCRIPT_DIR}/logs'
    if not os.path.exists(logDir):
            os.makedirs(logDir)

    if to_file:
        # Set the handler that logs to file
        log_name = f'{logger_name}.{datetime.now().strftime("%m-%d-%Y")}.log'
        logfile_path = os.path.join(logDir, log_name)
        fh = logging.FileHandler(logfile_path)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    # Set the handler that logs to stdout
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def handle_errors(error):
    exception_type, exception_object, exception_traceback = sys.exc_info()
    filename = exception_traceback.tb_frame.f_code.co_filename
    line_number = exception_traceback.tb_lineno

    error_msg = textwrap.dedent(f"""```
    Exception occured:
        Type: {exception_type}
        Object: {exception_object}
        Where?: {filename}   Line num: {line_number}
    ```""")

    return error_msg


def send_notif(url, content, discord_id):
    if url:
        content_header = f"---------------<@{discord_id if discord_id else 'NEW MSG'}>---------------\n"
        
        if len(content) >= 1999:
            files = {'heros.txt': content}
            resp = requests.post(url, data={"content": content_header}, files=files)
        else:
            headers = {"Content-type": "application/json"}
            content = content_header + content
            resp = requests.post(url, headers=headers, json={"content": content})
    else:
        print("No webhook configured in config.yaml.")