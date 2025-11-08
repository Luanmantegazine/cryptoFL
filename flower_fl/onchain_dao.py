import json, os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_utils import keccak

from deployments import resolve_address

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


# ✅ Guarde o ABI numa variável global para reusar nos decoders de eventos
DAO_ABI = _abi(DAO_ABI_PATH)

DAO_ADDRESS = resolve_address(
    os.getenv("DAO_ADDRESS"),
    w3,
    name="dao",
    deployments_dir=DEPLOYMENTS_DIR,
    ignition_dir=IGNITION_DIR,
)

DAO = w3.eth.contract(
    address=Web3.to_checksum_address(DAO_ADDRESS),
    abi=DAO_ABI,
)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


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


# --- DAO calls (mantidos) ---

def register_requester():
    return _send(DAO.functions.registerRequester())


def register_trainer(description: str, specification: Tuple):
    return _send(DAO.functions.registerTrainer(description, specification))


def match_trainers(job_requirements: Tuple) -> List[str]:
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


def get_pending_offer_ids_for(trainer_owner_addr: str):
    # ⚠️ Só funcione se existir MESMO no ABI do DAO!
    return DAO.functions.getPendingOfferIdsFor(
        Web3.to_checksum_address(trainer_owner_addr)
    ).call()


def accept_offer(offer_id: int):
    return _send(DAO.functions.AcceptOffer(int(offer_id)))


def sign_job_contract(job_addr: str, total_amount_wei: int = 0):
    return _send(DAO.functions.signJobContract(Web3.to_checksum_address(job_addr)), value_wei=total_amount_wei)


def get_offer_details(offer_id: int):
    return DAO.functions.getOfferDetailsFor(acct.address, int(offer_id)).call({"from": acct.address})


def get_requester_contract(account: str) -> str:
    return DAO.functions.requesters(Web3.to_checksum_address(account)).call()


def get_trainer_contract(account: str) -> str:
    return DAO.functions.trainers(Web3.to_checksum_address(account)).call()


def _find_event_abi_by_name_prefix(prefix: str):
    pref = prefix.lower()
    for item in DAO_ABI:
        if item.get("type") == "event" and item.get("name", "").lower().startswith(pref):
            return item
    return None


def _iter_event_decoders_from_abi(abi):
    """Cria decoders para TODOS os eventos do ABI."""
    decoders = []
    for item in abi:
        if item.get("type") == "event":
            tmp = w3.eth.contract(abi=[item])
            decoders.append(tmp.events[item["name"]])
    return decoders


def extract_offer_id_from_logs(logs) -> int | None:
    """
    Tenta decodificar o ID de oferta a partir de qualquer evento emitido pelo DAO
    na tx de MakeOffer. Heurísticas:
      1) usar campos chamados 'id', 'offerId', 'offerID', 'offer_id';
      2) se não achar, pegar o primeiro inteiro não-negativo dos args;
      3) se ainda não achar, tentar tópicos não-endereço como uint.
    """
    # garanta que você tem `DAO_ABI` global carregado no módulo
    decoders = _iter_event_decoders_from_abi(DAO.abi)

    # 1) decodifica eventos pelo ABI
    for log in logs:
        if log.get("address", "").lower() != DAO.address.lower():
            continue
        for dec in decoders:
            try:
                ev = dec().process_log(log)
                args = ev["args"]
                # nomes “óbvios”
                for key in ("id", "offerId", "offerID", "offer_id"):
                    if key in args and isinstance(args[key], int) and args[key] >= 0:
                        return int(args[key])
                # senão: primeiro int não-negativo
                for k, v in args.items():
                    if isinstance(v, int) and v >= 0:
                        return int(v)
            except Exception:
                pass

    # 2) fallback bruto: tenta extrair uint dos tópicos (se o id for indexed)
    from eth_utils import big_endian_to_int
    ZERO_ADDR_TOPIC_PREFIX = "0x000000000000000000000000"

    for log in logs:
        if log.get("address", "").lower() != DAO.address.lower():
            continue
        topics = [t.hex() if hasattr(t, "hex") else str(t) for t in log.get("topics", [])]
        # topics[0] é o keccak do evento; os demais podem trazer indexed params.
        for t in topics[1:]:
            # ignorar se parecer endereço (tem o prefixo de 12 bytes zeros + 20 bytes address)
            if t.startswith(ZERO_ADDR_TOPIC_PREFIX) and len(t) == 66:
                # é um endereço indexado, ignore
                continue
            try:
                val = big_endian_to_int(bytes.fromhex(t[2:]))
                if val >= 0:
                    return int(val)
            except Exception:
                pass

    return None
