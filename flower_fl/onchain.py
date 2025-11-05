import json, os
from typing import Any, Dict
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_utils import keccak

load_dotenv()

RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
DAO_ADDRESS = os.getenv("DAO_ADDRESS")
DAO_ABI_PATH = os.getenv("DAO_ABI_PATH")

assert RPC_URL and PRIVATE_KEY, "Defina RPC_URL e PRIVATE_KEY no .env"
assert DAO_ADDRESS and DAO_ABI_PATH, "Defina DAO_ADDRESS e DAO_ABI_PATH no .env"

w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
acct = Account.from_key(PRIVATE_KEY)
DAO = None


def _load_abi(path: str):
    with open(path, "r") as f:
        j = json.load(f)
        return j["abi"] if isinstance(j, dict) and "abi" in j else j


def _contract():
    global DAO
    if DAO is None:
        abi = _load_abi(DAO_ABI_PATH)
        DAO = w3.eth.contract(
            address=Web3.to_checksum_address(DAO_ADDRESS),
            abi=abi,
        )
    return DAO


def _dynamic_tx(fn, value: int = 0):
    nonce = w3.eth.get_transaction_count(acct.address)
    base = fn.build_transaction({"from": acct.address, "nonce": nonce, "value": value})
    gas = w3.eth.estimate_gas(base)
    gas_price = w3.eth.gas_price
    max_priority = min(gas_price // 10 or 1, w3.to_wei("2", "gwei"))
    tx = {
        **base,
        "gas": int(gas * 120 // 100 + 1),
        "maxFeePerGas": gas_price + max_priority,
        "maxPriorityFeePerGas": max_priority,
        "chainId": w3.eth.chain_id,
    }
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash)
    gas_eth = rcpt.gasUsed * rcpt.effectiveGasPrice / 1e18
    return {"hash": tx_hash.hex(), "gasUsed": rcpt.gasUsed, "gasETH": gas_eth}


def update_global_model(job_addr: str, cid: str, encrypted: bytes = b"") -> Dict[str, Any]:
    dao = _contract()
    cid_hash = keccak(text=cid)
    fn = dao.functions.publishGlobalModel(Web3.to_checksum_address(job_addr), cid_hash, encrypted)
    return _dynamic_tx(fn)


def send_update(job_addr: str, cid: str, encrypted: bytes = b"") -> Dict[str, Any]:
    dao = _contract()
    cid_hash = keccak(text=cid)
    fn = dao.functions.recordClientUpdate(Web3.to_checksum_address(job_addr), cid_hash, encrypted)
    return _dynamic_tx(fn)
