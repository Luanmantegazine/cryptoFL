import flwr as fl
import numpy as np
from web3 import Web3

# --- 1. Configuração Web3 (Plano de Controle) ---
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))  # Ex: Conexão com Arbitrum
w3.eth.default_account = "0x..."  # Endereço da carteira do Requester
requester_private_key = "..."  # Chave privada do Requester

# ABIs e Endereços dos contratos
job_contract_abi = [...]
job_contract_address = "0x..."  # Endereço do JobContract obtido após AcceptOffer

# Conectar ao contrato
job_contract = w3.eth.contract(address=job_contract_address, abi=job_contract_abi)

# Ler os parâmetros do trabalho do contrato
try:
    NUM_ROUNDS = job_contract.functions.numberOfUpdates().call()
    VALUE_PER_UPDATE = job_contract.functions.valueByUpdate().call()
    print(f"Lendo do JobContract: {NUM_ROUNDS} rodadas, pagando {VALUE_PER_UPDATE} por rodada.")
except Exception as e:
    print(f"Erro ao ler contrato: {e}")
    exit()


# --- 2. Lógica de Agregação (Plano de Dados) ---

# Esta classe personalizada irá interagir com o contrato
class BlockchainStrategy(fl.server.strategy.FedAvg):

    def aggregate_fit(self, server_round, results, failures):
        """Agrega os resultados do 'fit' e reporta à blockchain."""

        print(f"Servidor: Recebendo {len(results)} atualizações na rodada {server_round}.")

        # 1. Agrega os modelos (lógica padrão do FedAvg)
        aggregated_parameters = super().aggregate_fit(server_round, results, failures)

        if aggregated_parameters is not None:
            # 2. Chama o Contrato (Plano de Controle)
            # Se a agregação foi bem-sucedida, chama newUpdate() para pagar os Trainers
            try:
                print(f"Servidor: Reportando Rodada {server_round} para a Blockchain...")
                nonce = w3.eth.get_transaction_count(w3.eth.default_account)

                tx = job_contract.functions.newUpdate().build_transaction({
                    'from': w3.eth.default_account,
                    'nonce': nonce,
                    'gas': 200000,
                    'gasPrice': w3.to_wei('1', 'gwei')  # Preço do gás (ex: Arbitrum)
                })

                signed_tx = w3.eth.account.sign_transaction(tx, requester_private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

                print(f"Servidor: Transação newUpdate() enviada: {tx_hash.hex()}")

            except Exception as e:
                print(f"Servidor: ERRO ao chamar newUpdate: {e}")
                # (Lógica de retry pode ser necessária aqui)

        return aggregated_parameters


# --- 3. Iniciar o Servidor Flower ---

# O Requester (Servidor) define o filtro inicial (Kernel)
# Este é o "modelo global" inicial
initial_filter = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
initial_parameters = fl.common.ndarrays_to_parameters([initial_filter])

# Configura a estratégia
strategy = BlockchainStrategy(
    initial_parameters=initial_parameters,
    min_fit_clients=1,  # Número mínimo de trainers por rodada (definido no contrato)
    min_available_clients=1,  # Número total de trainers no job
)

print(f"Iniciando Servidor Flower (Requester) por {NUM_ROUNDS} rodadas...")
print("Aguardando Trainers (Clientes Flower) se conectarem...")

# Inicia o servidor
fl.server.start_server(
    server_address="0.0.0.0:8080",  # Este IP deve ser público (o 'serverEndpoint' da oferta)
    config=fl.server.ServerConfig(num_rounds=NUM_ROUNDS),
    strategy=strategy
)

print("Trabalho concluído. Verifique o JobContract para pagamentos.")