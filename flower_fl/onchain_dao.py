import json, os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_utils import keccak

from .deployments import resolve_address

load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
DAO_ABI_PATH = os.getenv("DAO_ABI_PATH")
DEPLOYMENTS_DIR = os.getenv("DEPLOYMENTS_DIR", "deployments")
IGNITION_DIR = os.getenv("IGNITION_DIR", "ignition/deployments")

assert RPC_URL and PRIVATE_KEY, "Defina RPC_URL e PRIVATE_KEY no .env"
assert DAO_ABI_PATH, "Defina DAO_ABI_PATH no .env"

w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
acct = Account.from_key(PRIVATE_KEY)


def _abi(path: str):
    data = json.loads(Path(path).read_text())
    return data["abi"] if isinstance(data, dict) and "abi" in data else data


DAO_ADDRESS = resolve_address(
    os.getenv("DAO_ADDRESS"),
    w3,
    name="dao",
    deployments_dir=DEPLOYMENTS_DIR,
    ignition_dir=IGNITION_DIR,
)

DAO = w3.eth.contract(
    address=Web3.to_checksum_address(DAO_ADDRESS),
    abi=_abi(DAO_ABI_PATH),
)

def _send(fn, value_wei: int = 0) -> Dict[str, Any]:
    nonce = w3.eth.get_transaction_count(acct.address)
    base = fn.build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "value": value_wei,
    })
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
    return {
        "hash": tx_hash.hex(),
        "gasUsed": rcpt.gasUsed,
        "gasETH": rcpt.gasUsed * rcpt.effectiveGasPrice / 1e18,
        "logs": rcpt.logs,
    }

# --- DAO calls ---

def register_requester():
    fn = DAO.functions.registerRequester()
    return _send(fn)

def register_trainer(description: str, specification: Tuple):
    """
    specification deve seguir o layout de DataTypes.Specification do seu contrato.
    Ex.: (datasetSize, processor, ram, cpu, tagsArray)
    Ajuste a tupla conforme o struct real.
    """
    fn = DAO.functions.registerTrainer(description, specification)
    return _send(fn)

def match_trainers(job_requirements: Tuple) -> List[str]:
    """
    job_requirements = tupla no formato do seu DataTypes.JobRequirements.
    Retorna array de addresses.
    """
    return DAO.functions.matchTrainers(job_requirements).call()

def make_offer(description: str, model_cid: str, value_by_update_wei: int,
               number_of_updates: int, trainer_addr: str, server_endpoint: str,
               encrypted_metadata: bytes = b""):
    model_hash = keccak(text=model_cid)
    endpoint_hash = keccak(text=server_endpoint)
    fn = DAO.functions.MakeOffer(
        description,
        model_hash,
        endpoint_hash,
        encrypted_metadata,
        value_by_update_wei,
        number_of_updates,
        Web3.to_checksum_address(trainer_addr),
    )
    return _send(fn)

def get_pending_offers() -> list:
    return DAO.functions.getPendingOffers().call()

def accept_offer(offer_id: int):
    fn = DAO.functions.AcceptOffer(offer_id)
    return _send(fn)

def sign_job_contract(job_addr: str, total_amount_wei: int = 0):
    fn = DAO.functions.signJobContract(Web3.to_checksum_address(job_addr))
    return _send(fn, value_wei=total_amount_wei)
