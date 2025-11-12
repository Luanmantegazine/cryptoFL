import os, numpy as np
import flwr as fl
from typing import List
from dotenv import load_dotenv
from onchain_job import job_send_update

from ipfs import ipfs_get_numpy, ipfs_add_numpy
from utils import init_weights

load_dotenv()

JOB_ADDR = os.getenv("JOB_ADDR")
NUM_EXAMPLES = int(os.getenv("NUM_EXAMPLES", "100"))

assert JOB_ADDR, "Configure JOB_ADDR no .env (execute o main.py primeiro)"


def local_train(params: List[np.ndarray]) -> List[np.ndarray]:
    print("[FL] Treinando localmente...")
    return [w + 0.01 * np.random.randn(*w.shape) for w in params]


def local_eval(params: List[np.ndarray]) -> tuple[float, float]:
    return float(np.random.rand()), float(np.random.rand())


class Client(fl.client.NumPyClient):

    def __init__(self):
        # Armazenar os pesos do modelo localmente
        self.model_weights = init_weights()

    def get_parameters(self, config):
        if "cid_global" in config:
            cid = config["cid_global"]
            print(f"[On-chain] Baixando modelo global do IPFS: {cid}")
            arrs = ipfs_get_numpy(cid)
            self.model_weights = arrs # Atualiza o modelo local
            return arrs
        else:
            # SENÃO, O SERVIDOR ESTÁ PEDINDO OS PARÂMETROS INICIAIS
            print("[FL] Servidor pediu parâmetros iniciais.")
        return self.model_weights

    def fit(self, parameters, config):
        self.model_weights = parameters
        updated = local_train(self.model_weights)
        self.model_weights = updated # Salva o modelo treinado

        # Salvar o resultado local no IPFS
        cid_up = ipfs_add_numpy(updated, "client_update.npz")
        print(f"[On-chain] Update local salvo no IPFS: {cid_up}")

        # Chamar 'recordClientUpdate' no contrato para ser pago
        r = job_send_update(JOB_ADDR, cid_up)
        print(f"[JOB {JOB_ADDR}] SendUpdate tx={r['hash']} gas={r['gasETH']:.8f} ETH")

        return updated, NUM_EXAMPLES, {"cid": cid_up}

    def evaluate(self, parameters, config):
        loss, acc = local_eval(parameters)
        return loss, 100, {"accuracy": acc}


def main():
    print(f"[Flower] Conectando ao servidor em 0.0.0.0:8080...")
    fl.client.start_client(server_address="0.0.0.0:8080", client=Client().to_client())


if __name__ == "__main__":
    main()