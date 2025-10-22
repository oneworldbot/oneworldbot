from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

# configuration populated by init_web3()
_w3 = None
OWC_CONTRACT = None
PRIVATE_KEY = None


def init_web3():
    """Initialize web3 instance from environment variables.
    Call this at runtime (for example in main()) after loading .env.
    """
    global _w3, OWC_CONTRACT, PRIVATE_KEY
    BSC_RPC = os.environ.get("BSC_RPC")
    OWC_CONTRACT = os.environ.get("OWC_CONTRACT_ADDRESS")
    PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
    if not BSC_RPC:
        _w3 = None
        return False
    _w3 = Web3(Web3.HTTPProvider(BSC_RPC))
    return _w3.is_connected()


def get_w3():
    return _w3


def get_tx(tx_hash: str):
    if not _w3:
        return None
    try:
        return _w3.eth.get_transaction(tx_hash)
    except Exception:
        return None


def is_connected():
    return _w3.is_connected() if _w3 else False
