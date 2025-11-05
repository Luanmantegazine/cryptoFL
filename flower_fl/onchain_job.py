import os, json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
JOB_ABI_PATH = os.getenv("JOB_ABI_PATH")  # ex.: ./artifacts/contracts/JobContract.sol/JobContract.json

assert RPC_URL and PRIVATE_KEY and JOB_ABI_PATH, "Configure RPC_URL, PRIVATE_KEY e JOB_ABI_PATH no .env"

w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
acct = Account.from_key(PRIVATE_KEY)

def _load_abi(path: str):
    j = json.loads(Path(path).read_text())
    return j["abi"] if isinstance(j, dict) and "abi" in j else j

ABI = _load_abi(JOB_ABI_PATH)

def _job(addr: str):
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ABI)

def _send(fn) -> Dict[str, Any]:
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "gas": 1_800_000,
        "maxFeePerGas": w3.to_wei("0.2","gwei"),
        "maxPriorityFeePerGas": w3.to_wei("0.05","gwei"),
    })
    signed = acct.sign_transaction(tx)
    txh = w3.eth.send_raw_transaction(signed.rawTransaction)
    rc = w3.eth.wait_for_transaction_receipt(txh)
    return {"hash": txh.hex(), "gasUsed": rc.gasUsed, "gasETH": rc.gasUsed * rc.effectiveGasPrice / 1e18}

def job_update_global(job_addr: str, cid: str):
    job = _job(job_addr)
    # ⚠️ ajuste o nome exato conforme o ABI do JobContract:
    return _send(job.functions.UpdateGlobalModel(cid))

def job_send_update(job_addr: str, cid: str):
    job = _job(job_addr)
    # ⚠️ ajuste o nome exato conforme o ABI do JobContract:
    return _send(job.functions.SendUpdate(cid))