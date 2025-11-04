import os
import flwr as fl
import numpy as np
from dotenv import load_dotenv
from ipfs_wrap import ipfs_get_npz, ipfs_add_numpy_arrays
from hh_bridge import send_update

load_dotenv()
JOB_ID = int(os.getenv("JOB_ID", "1"))

def local_train(params: list[np.ndarray]) -> list[np.ndarray]:
    # Treino dummy: adiciona ruído pequeno (substitua por treino real)
    return [w + 0.01*np.random.randn(*w.shape) for w in params]

def local_evaluate(params: list[np.ndarray]) -> tuple[float, float]:
    # Dummy: perda/acc aleatórias (substitua pelo seu dataset)
    loss = float(np.random.rand())
    acc = float(np.random.rand())
    return loss, acc

class Client(fl.client.NumPyClient):
    def get_parameters(self, config):
        cid = config.get("cid_global")
        arrays, _ = ipfs_get_npz(cid)
        return arrays
    def fit(self, parameters, config):
        updated = local_train(parameters)
        cid_up = ipfs_add_numpy_arrays(updated, filename="client_update.npz")
        send_update(JOB_ID, cid_up)
        num_examples = 100  # dummy
        return updated, num_examples, {}
    def evaluate(self, parameters, config):
        loss, acc = local_evaluate(parameters)
        num_examples = 100
        return loss, num_examples, {"accuracy": acc}

def main():
    fl.client.start_numpy_client(server_address="0.0.0.0:8080", client=Client())

if __name__ == "__main__":
    main()
