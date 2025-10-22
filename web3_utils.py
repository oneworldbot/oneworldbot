from web3 import Web3
import os
import time
import logging
from dotenv import load_dotenv
from web3.exceptions import TransactionNotFound

load_dotenv()

logger = logging.getLogger(__name__)

# configuration populated by init_web3()
_w3 = None
OWC_CONTRACT = None
PRIVATE_KEY = None


def init_web3(retries: int = 3, timeout: int = 10) -> bool:
    """Initialize web3 instance from environment variables.
    - retries: number of connection attempts
    - timeout: HTTP timeout in seconds for provider requests

    Returns True when connected, False otherwise. Logs details.
    """
    global _w3, OWC_CONTRACT, PRIVATE_KEY
    BSC_RPC = os.environ.get("BSC_RPC")
    OWC_CONTRACT = os.environ.get("OWC_CONTRACT_ADDRESS")
    PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

    if not BSC_RPC:
        logger.warning("BSC_RPC not set in environment; web3 not initialized")
        _w3 = None
        return False

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            # pass timeout to requests via request_kwargs if supported
            provider = Web3.HTTPProvider(BSC_RPC, request_kwargs={"timeout": timeout})
            _w3 = Web3(provider)
            connected = _w3.is_connected()
            if connected:
                logger.info("web3 connected to %s (attempt %d/%d)", BSC_RPC, attempt, retries)
                return True
            else:
                last_err = RuntimeError("web3 returned False for is_connected()")
                logger.warning("web3 not connected on attempt %d/%d", attempt, retries)
        except Exception as e:
            last_err = e
            logger.exception("web3 init attempt %d failed", attempt)
        time.sleep(min(2 ** attempt, 10))

    logger.error("Failed to initialize web3 after %d attempts: %s", retries, getattr(last_err, "__str__", lambda: str(last_err))())
    _w3 = None
    return False


def get_w3():
    """Return the initialized Web3 instance or None."""
    return _w3


def is_connected() -> bool:
    return bool(_w3 and _w3.is_connected())


def get_tx(tx_hash: str):
    """Return transaction dict or None.
    Handles missing connection and TransactionNotFound.
    """
    if not _w3:
        logger.debug("get_tx called but web3 not initialized")
        return None
    try:
        return _w3.eth.get_transaction(tx_hash)
    except TransactionNotFound:
        logger.debug("Transaction %s not found", tx_hash)
        return None
    except Exception:
        logger.exception("Error fetching transaction %s", tx_hash)
        return None


def get_receipt(tx_hash: str, wait: bool = False, timeout: int = 30):
    """Return transaction receipt or None. If wait=True, poll until timeout (seconds)."""
    if not _w3:
        logger.debug("get_receipt called but web3 not initialized")
        return None
    try:
        if wait:
            start = time.time()
            while True:
                try:
                    receipt = _w3.eth.get_transaction_receipt(tx_hash)
                    return receipt
                except TransactionNotFound:
                    if time.time() - start > timeout:
                        logger.debug("Timed out waiting for receipt %s", tx_hash)
                        return None
                    time.sleep(2)
        else:
            return _w3.eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        logger.debug("Receipt for %s not found", tx_hash)
        return None
    except Exception:
        logger.exception("Error fetching receipt %s", tx_hash)
        return None


def get_balance(address: str):
    """Return native balance (in Wei) for address or None."""
    if not _w3:
        logger.debug("get_balance called but web3 not initialized")
        return None
    try:
        checksum = _w3.to_checksum_address(address)
        return _w3.eth.get_balance(checksum)
    except Exception:
        logger.exception("Error getting balance for %s", address)
        return None


def to_checksum(address: str):
    if not _w3:
        return address
    try:
        return _w3.to_checksum_address(address)
    except Exception:
        return address
