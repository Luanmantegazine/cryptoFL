import sys
import os
from dotenv import load_dotenv, find_dotenv, set_key
from eth_account import Account

# Importa as funções e variáveis do seu script onchain_dao
# Certifique-se que o nome do módulo está correto (flower_fl.onchain_dao)
try:
    from onchain_dao import (
        register_requester,
        register_trainer,
        make_offer,
        get_pending_offers,
        accept_offer,
        sign_job_contract,
        w3,
        acct
    )
except ImportError:
    print("Erro: Não foi possível importar 'flower_fl.onchain_dao'.")
    print("Certifique-se de que está executando o script do diretório raiz 'CriptoFL' (ex: python flower_fl/main.py)")
    sys.exit(1)

# --- Endereços do seu 'npx hardhat node' ---
ADDR_REQUESTER = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
KEY_REQUESTER = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

ADDR_TRAINER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
KEY_TRAINER = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

# Valor total do Job (0.003 ETH)
# (0.001 ETH por rodada * 3 rodadas)
JOB_VALUE_WEI = w3.to_wei(0.003, "ether")


def switch_env_user(private_key):
    """Muda a PRIVATE_KEY no arquivo .env"""
    env_file = find_dotenv()
    if not env_file:
        print("!!! ERRO: Arquivo .env não encontrado.")
        return False

    print(f"\n... Trocando usuário no .env para a chave: {private_key[:10]}...")
    set_key(env_file, "PRIVATE_KEY", private_key)
    # Recarrega o .env nos módulos que o importam
    os.environ["PRIVATE_KEY"] = private_key
    global acct
    acct = Account.from_key(private_key)
    # Recarrega a conta no módulo onchain_dao
    # from flower_fl import onchain_dao
    # onchain_dao.acct = acct

    print(f"... Usuário trocado. Endereço ativo: {acct.address}")
    return True


def parse_logs_for_job_address(logs):
    """ Encontra o endereço do JobContract no log do evento JobContractCreated """
    # O endereço do Job é o segundo tópico (topics[1]) do evento
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
    print("4. Buscando ofertas pendentes...")
    offers = get_pending_offers()
    if not offers:
        print("!!! ERRO: Nenhuma oferta encontrada.")
        return

    offer_id = offers[0]  # O ID é o primeiro elemento da struct Offer
    print(f"   -> Oferta {offer_id} encontrada.")
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
    print(">>> FASE 2 COMPLETA! JOB CRIADO E FINCIADO! <<<")
    print(f"O endereço do JobContract é: {job_address}")
    print("***********************************************")

    env_file = find_dotenv()
    set_key(env_file, "JOB_ADDRS", job_address)
    set_key(env_file, "JOB_ADDR", job_address)
    # Deixa o .env pronto para o server/cliente (Conta #0)
    switch_env_user(KEY_REQUESTER)

    print("\n.env atualizado. Pronto para a FASE 3.")
    print("No Terminal 2, rode: python flower_fl/server.py")
    print("No Terminal 3, rode: python flower_fl/client.py")


if __name__ == "__main__":
    run_all_phases()