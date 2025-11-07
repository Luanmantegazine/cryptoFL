import sys
import os
from dotenv import load_dotenv, find_dotenv, set_key
from eth_account import Account

# --- CORREÇÃO DE IMPORTAÇÃO ---
# Importa o módulo 'onchain_dao' primeiro
try:
    import onchain_dao
except ImportError:
    print("Erro: Não foi possível importar 'onchain_dao'.")
    print("Certifique-se de que 'main.py' e 'onchain_dao.py' estão na mesma pasta.")
    sys.exit(1)

# Agora importa as funções e variáveis específicas
from onchain_dao import (
    register_requester,
    register_trainer,
    make_offer,
    get_pending_offers,
    accept_offer,
    sign_job_contract,
    w3
)

# --- FIM DA CORREÇÃO ---

# --- Endereços do seu 'npx hardhat node' ---
ADDR_REQUESTER = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
KEY_REQUESTER = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

ADDR_TRAINER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
KEY_TRAINER = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

JOB_VALUE_WEI = w3.to_wei(0.003, "ether")
acct = Account.from_key(os.getenv("PRIVATE_KEY"))  # Define a conta local


def switch_env_user(private_key):
    """Muda a PRIVATE_KEY no arquivo .env E atualiza os módulos"""
    env_file = find_dotenv()
    if not env_file:
        print("!!! ERRO: Arquivo .env não encontrado.")
        return False

    print(f"\n... Trocando usuário no .env para a chave: {private_key[:10]}...")
    set_key(env_file, "PRIVATE_KEY", private_key)
    os.environ["PRIVATE_KEY"] = private_key

    # --- CORREÇÃO CRÍTICA ---
    # Atualiza a conta neste script E no módulo importado
    global acct
    acct = Account.from_key(private_key)
    onchain_dao.acct = acct  # <-- ESTA É A LINHA QUE CORRIGE O BUG
    # --- FIM DA CORREÇÃO ---

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
    r_requester = register_requester()
    print(f"   -> Tx: {r_requester['hash']}")

    # --- Parte 2: Registro do Treinador ---
    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 2: Ações do Treinador ({acct.address}) ---")
    print("2. Registrando Treinador...")
    spec = ("Processador Exemplo", "16GB", "8 Cores")
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

    # --- Parte 4: Aceite do Treinador ---
    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 4: Ações do Treinador ({acct.address}) ---")
    print("4. Buscando IDs de ofertas pendentes...")
    offer_ids = get_pending_offers()  # Deve funcionar agora
    if not offer_ids:
        print("!!! ERRO: Nenhuma oferta encontrada.")
        return

    offer_id = offer_ids[0]
    print(f"   -> ID de oferta {offer_id} encontrado.")

    print(f"5. Aceitando oferta {offer_id}...")
    r_accept = accept_offer(offer_id)
    print(f"   -> Tx: {r_accept['hash']}")

    job_address = parse_logs_for_job_address(r_accept['logs'])
    if not job_address:
        print("!!! ERRO: Não foi possível encontrar o endereço do JobContract!")
        return
    print(f"   -> JobContract criado em: {job_address}")

    # --- Parte 5: Financiamento do Job (Requisitante) ---
    if not switch_env_user(KEY_REQUESTER): return
    print(f"\n--- Parte 5: Financiamento do Job ({acct.address}) ---")
    print(f"6. Assinando e depositando {w3.from_wei(JOB_VALUE_WEI, 'ether')} ETH no Job...")
    r_sign_requester = sign_job_contract(job_address, total_amount_wei=JOB_VALUE_WEI)
    print(f"   -> Tx: {r_sign_requester['hash']}")

    # --- Parte 6: Assinatura do Job (Treinador) ---
    if not switch_env_user(KEY_TRAINER): return
    print(f"\n--- Parte 6: Assinatura final do Job ({acct.address}) ---")
    print(f"7. Treinador assinando o Job...")
    r_sign_trainer = sign_job_contract(job_address, total_amount_wei=0)
    print(f"   -> Tx: {r_sign_trainer['hash']}")

    # --- Conclusão ---
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