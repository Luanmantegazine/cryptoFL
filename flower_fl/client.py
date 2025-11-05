import flwr as fl
import numpy as np
from web3 import Web3

# --- 1. Configuração Web3 (Plano de Controle) ---
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))  # Ex: Conexão com Arbitrum
w3.eth.default_account = "0x..."  # Endereço da carteira do Trainer
trainer_private_key = "..."

# ABIs e Endereços dos contratos
job_contract_abi = [...]
job_contract_address = "0x..."  # Endereço do JobContract obtido após AcceptOffer

# Conectar ao contrato
job_contract = w3.eth.contract(address=job_contract_address, abi=job_contract_abi)

# --- 2. Lógica de Treinamento Local (Plano de Dados) ---

# Carrega os dados locais do Trainer
# (Esta é a 'imagem' e a 'linha' pela qual este trainer é responsável)
imagem_local = np.array([[0, 0, 0, 0, 0, 0, 0],
                         [0, 119, 43, 104, 62, 83, 0],  # 1
                         [0, 64, 119, 72, 69, 85, 0],  # 2
                         [0, 137, 66, 46, 143, 85, 0],  # 3
                         [0, 132, 81, 30, 28, 54, 0],  # 4
                         [0, 38, 37, 113, 141, 60, 0],  # 5
                         [0, 0, 0, 0, 0, 0, 0]])

# Este Trainer é responsável pela linha 2 (exemplo)
LINHA_RESPONSAVEL = 2


def convolution(img, filter, row):
    """Sua lógica de convolução local."""
    result = []
    k = filter.shape[0]
    for c in range(0, len(img[row]) - 2):
        mat = img[row:row + k, c:c + k]
        result.append(np.sum(np.multiply(mat, filter)))

    # Em um cenário real de ML, você atualizaria o 'filter' (pesos)
    # com backpropagation.
    # No seu caso de convolução, nós apenas usamos o filtro.
    # Para simular um "update", vamos apenas retornar o filtro recebido.
    # Em um cenário real, você retornaria o filtro *atualizado*.

    updated_filter = filter  # Simulação
    num_examples = len(result)

    print(f"Trainer: Convolução da linha {row} concluída. Resultado: {result}")

    return updated_filter, num_examples


# Define o Cliente Flower
class ConvolutionClient(fl.client.NumPyClient):

    def get_parameters(self, config):
        # (Não usado neste exemplo simples, o servidor envia primeiro)
        return []

    def fit(self, parameters, config):
        """Executa o treinamento/computação local."""

        # 'parameters' é o filtro/modelo global recebido do servidor
        global_filter = parameters[0]

        print("Trainer: Recebeu filtro global do servidor.")

        # Executa a lógica de convolução local
        updated_filter, num_examples = convolution(
            imagem_local,
            global_filter,
            LINHA_RESPONSAVEL
        )

        # Retorna o modelo/filtro "atualizado" para o servidor
        # (Junto com o número de exemplos para o FedAvg)
        return [updated_filter], num_examples, {}

    def evaluate(self, parameters, config):
        # (Opcional: avaliar o modelo global)
        return 0.0, 0, {"accuracy": 0.9}  # Fictício


# --- 3. Iniciar o Cliente Flower ---

try:
    # O Cliente lê o endereço do Servidor do contrato!
    SERVER_ENDPOINT = job_contract.functions.getServerEndpoint().call()
    print(f"Trainer: Lendo endpoint do servidor do contrato: {SERVER_ENDPOINT}")

    if not SERVER_ENDPOINT:
        raise Exception("Endpoint do servidor está vazio no contrato.")

    # Inicia o cliente e se conecta ao servidor
    fl.client.start_numpy_client(
        server_address=SERVER_ENDPOINT,
        client=ConvolutionClient()
    )
    print("Trainer: Conexão com o servidor encerrada.")

except Exception as e:
    print(f"Trainer: ERRO ao iniciar cliente: {e}")