import os, numpy as np
import flwr as fl
from typing import List
from dotenv import load_dotenv
from onchain_job import job_send_update

from ipfs import ipfs_get_numpy, ipfs_add_numpy

load_dotenv()

JOB_ADDR = os.getenv("JOB_ADDR")
NUM_EXAMPLES = int(os.getenv("NUM_EXAMPLES", "100"))

assert JOB_ADDR, "Configure JOB_ADDR no .env"

def local_train(params: List[np.ndarray]) -> List[np.ndarray]:
    # Demonstração: treino “fake” (adicione ruído). Troque por treino real.
    return [w + 0.01*np.random.randn(*w.shape) for w in params]

def local_eval(params: List[np.ndarray]) -> tuple[float, float]:
    # Demonstração: métricas aleatórias
    return float(np.random.rand()), float(np.random.rand())

class Client(fl.client.NumPyClient):
    def get_parameters(self, config):
        cid = config["cid_global"]
        arrs = ipfs_get_numpy(cid)
        return arrs

    def fit(self, parameters, config):
        updated = local_train(parameters)
        cid_up = ipfs_add_numpy(updated, "client_update.npz")
        r = job_send_update(JOB_ADDR, cid_up)
        print(f"[JOB {JOB_ADDR}] SendUpdate tx={r['hash']} gas={r['gasETH']:.8f} ETH")
        return updated, NUM_EXAMPLES, {"cid": cid_up}

    def evaluate(self, parameters, config):
        loss, acc = local_eval(parameters)
        return loss, 100, {"accuracy": acc}

def main():
    fl.client.start_numpy_client(server_address="0.0.0.0:8080", client=Client())

if __name__ == "__main__":
    main()
