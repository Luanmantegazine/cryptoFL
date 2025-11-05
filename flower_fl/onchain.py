import json, os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

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
            abi=abi
        )
    return DAO

def _build_and_send(fn):
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "gas": 1_800_000,
        "maxFeePerGas": w3.to_wei("0.15", "gwei"),
        "maxPriorityFeePerGas": w3.to_wei("0.05", "gwei")
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash)
    gas_eth = rcpt.gasUsed * rcpt.effectiveGasPrice / 1e18
    return {"hash": tx_hash.hex(), "gasUsed": rcpt.gasUsed, "gasETH": gas_eth}

def update_global_model(job_id: int, cid: str) -> Dict[str, Any]:
    dao = _contract()
    # Ajuste o nome do método conforme seu contrato
    fn = dao.functions.UpdateGlobalModel(job_id, cid)
    return _build_and_send(fn)

def send_update(job_id: int, cid: str) -> Dict[str, Any]:
    dao = _contract()
    # Ajuste o nome conforme seu contrato
    fn = dao.functions.SendUpdate(cid, job_id)
    return _build_and_send(fn)
