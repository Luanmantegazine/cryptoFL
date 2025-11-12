import sys
import os
from dotenv import  find_dotenv, set_key
from eth_account import Account
from onchain_dao import extract_offer_id_from_logs

try:
    import onchain_dao
except ImportError:
    print("Erro: Não foi possível importar 'onchain_dao'.")
    print("Certifique-se de que 'main.py' e 'onchain_dao.py' estão na mesma pasta.")
    sys.exit(1)

from onchain_dao import (
    register_requester,
    register_trainer,
    make_offer,
    accept_offer,
    sign_job_contract,
    w3,
    get_requester_contract,
    get_trainer_contract,
    ZERO_ADDRESS,
)

# --- Endereços do seu 'npx hardhat node' ---
ADDR_REQUESTER = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
KEY_REQUESTER = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

ADDR_TRAINER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
KEY_TRAINER = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

JOB_VALUE_WEI = w3.to_wei(0.003, "ether")
acct = Account.from_key(os.getenv("PRIVATE_KEY"))


def switch_env_user(private_key):
    env_file = find_dotenv()
    if not env_file:
        print("!!! ERRO: Arquivo .env não encontrado.")
        return False

    print(f"\n... Trocando usuário no .env para a chave: {private_key[:10]}...")
    set_key(env_file, "PRIVATE_KEY", private_key)
    os.environ["PRIVATE_KEY"] = private_key

    global acct
    acct = Account.from_key(private_key)
    onchain_dao.acct = acct

    print(f"... Usuário trocado. Endereço ativo: {acct.address}")
    return True


def parse_logs_for_job_address(logs):
    if logs:
        job_addr_raw = logs[0]['topics'][1].hex()
        job_addr = "0x" + job_addr_raw[-40:]
        return w3.to_checksum_address(job_addr)
    return None


def run_all_phases():
    print(f"--- FASE 2: Iniciando criação do Job ---")

    # --- Parte 1: Registro do Requisitante ---
    if not switch_env_user(KEY_REQUESTER): return
    print(f"\n--- Parte 1: Ações do Requisitante ({acct.address}) ---")
    print("1. Registrando Requisitante...")
    requester_contract = get_requester_contract(acct.address)
    if requester_contract and requester_contract != ZERO_ADDRESS:
        print(f"   -> Requisitante já registrado. Contrato: {requester_contract}")
    else:
        r_requester = register_requester()
        print(f"   -> Tx: {r_requester['hash']}")

    # --- Parte 2: Registro do Treinador ---
    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 2: Ações do Treinador ({acct.address}) ---")
    print("2. Registrando Treinador...")
    spec = ("Processador Exemplo", "16GB", "8 Cores")
    trainer_contract = get_trainer_contract(acct.address)
    if trainer_contract and trainer_contract != ZERO_ADDRESS:
        print(f"   -> Treinador já registrado. Contrato: {trainer_contract}")
    else:
        r_trainer = register_trainer("Treinador de IA", spec)
        print(f"   -> Tx: {r_trainer['hash']}")

    # --- Parte 3: Oferta do Requisitante ---
    if not switch_env_user(KEY_REQUESTER): return
    print(f"\n--- Parte 3: Ações do Requisitante ({acct.address}) ---")
    print(f"3. Fazendo oferta para o Treinador (AGORA REGISTRADO) ({ADDR_TRAINER})...")
    r_offer = make_offer(
        description="Treinamento de modelo de imagem",
        model_cid="bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi",
        value_by_update_wei=w3.to_wei(0.001, "ether"),
        number_of_updates=3,
        trainer_addr=ADDR_TRAINER,
        server_endpoint="0.0.0.0:8080"
    )
    print(f"   -> Tx: {r_offer['hash']}")

    offer_id = extract_offer_id_from_logs(r_offer["logs"])
    if offer_id is None:
        print("!!! ERRO: Não consegui extrair o offerId dos eventos do DAO. Vamos inspecionar os logs:")
        for i, lg in enumerate(r_offer["logs"]):
            print(
                f"- Log[{i}] addr={lg['address']} topics={[t.hex() if hasattr(t, 'hex') else t for t in lg['topics']]} data={lg['data']}")
        return
    print(f"   -> offerId = {offer_id}")

    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 4: Ações do Treinador ({acct.address}) ---")
    print(f"5. Aceitando oferta {offer_id}...")
    r_accept = accept_offer(int(offer_id))
    print(f"   -> Tx: {r_accept['hash']}")

    job_address = parse_logs_for_job_address(r_accept['logs'])
    if not job_address:
        print("!!! ERRO: Não foi possível encontrar o endereço do JobContract nos logs de AcceptOffer!")
        return
    print(f"   -> JobContract criado em: {job_address}")

    if not switch_env_user(KEY_REQUESTER): return
    print(f"\n--- Parte 5: Financiamento do Job ({acct.address}) ---")
    print(f"6. Assinando e depositando {w3.from_wei(JOB_VALUE_WEI, 'ether')} ETH no Job...")
    r_sign_requester = sign_job_contract(job_address, total_amount_wei=JOB_VALUE_WEI)
    print(f"   -> Tx: {r_sign_requester['hash']}")

    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 6: Assinatura final do Job ({acct.address}) ---")
    print(f"7. Treinador assinando o Job...")
    r_sign_trainer = sign_job_contract(job_address, total_amount_wei=0)
    print(f"   -> Tx: {r_sign_trainer['hash']}")

    print("\n***********************************************")
    print(">>> FASE 2 COMPLETA! JOB CRIADO E FINANCIADO! <<<")
    print(f"O endereço do JobContract é: {job_address}")
    print("***********************************************")

    env_file = find_dotenv()
    set_key(env_file, "JOB_ADDRS", job_address)
    set_key(env_file, "JOB_ADDR", job_address)
    switch_env_user(KEY_REQUESTER)

    print("\n.env atualizado. Pronto para a FASE 3.")
    print("No Terminal 2, rode: python -m flower_fl.server")
    print("No Terminal 3, rode: python -m flower_fl.client")


if __name__ == "__main__":
    run_all_phases()