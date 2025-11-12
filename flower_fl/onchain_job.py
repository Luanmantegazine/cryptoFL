import os, json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_utils import keccak

load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
JOB_ABI_PATH = os.getenv("JOB_ABI_PATH")

assert RPC_URL and PRIVATE_KEY and JOB_ABI_PATH, "Configure RPC_URL, PRIVATE_KEY e JOB_ABI_PATH no .env"

w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
acct = Account.from_key(PRIVATE_KEY)


def _load_abi(path: str):
    j = json.loads(Path(path).read_text())
    return j["abi"] if isinstance(j, dict) and "abi" in j else j


ABI = _load_abi(JOB_ABI_PATH)


def _job(addr: str):
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ABI)


def _send(fn, value_wei: int = 0) -> Dict[str, Any]:
    nonce = w3.eth.get_transaction_count(acct.address)
    base_tx = fn.build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "value": value_wei,
    })
    gas = w3.eth.estimate_gas(base_tx)
    gas_price = w3.eth.gas_price
    max_priority = min(gas_price // 10 or 1, w3.to_wei("2", "gwei"))
    tx = {
        **base_tx,
        "gas": int(gas * 120 // 100 + 1),
        "maxFeePerGas": gas_price + max_priority,
        "maxPriorityFeePerGas": max_priority,
        "chainId": w3.eth.chain_id,
    }
    signed = acct.sign_transaction(tx)
    txh = w3.eth.send_raw_transaction(signed.rawTransaction)
    rc = w3.eth.wait_for_transaction_receipt(txh)
    return {"hash": txh.hex(), "gasUsed": rc.gasUsed, "gasETH": rc.gasUsed * rc.effectiveGasPrice / 1e18}


def job_update_global(job_addr: str, cid: str, encrypted: bytes = b""):
    job = _job(job_addr)
    cid_hash = keccak(text=cid)
    return _send(job.functions.publishGlobalModel(cid_hash, encrypted))


def job_send_update(job_addr: str, cid: str, encrypted: bytes = b""):
    job = _job(job_addr)
    cid_hash = keccak(text=cid)
    return _send(job.functions.recordClientUpdate(cid_hash, encrypted))
