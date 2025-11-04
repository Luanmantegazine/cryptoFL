import os, time
import flwr as fl
import numpy as np
from typing import Dict, List, Tuple
from dotenv import load_dotenv
from ipfs_wrap import ipfs_add_numpy_arrays
from hh_bridge import update_global_model

load_dotenv()
JOB_ID = int(os.getenv("JOB_ID", "1"))
ROUNDS = int(os.getenv("ROUNDS", "3"))

# Modelo dummy: vetor de pesos (ex.: 3 camadas)
INITIAL_WEIGHTS = [np.zeros((32, 32)), np.zeros((32,)), np.zeros((10, 32))]

def save_and_publish_global(weights: List[np.ndarray]) -> str:
    cid = ipfs_add_numpy_arrays(weights, filename=f"global_round.npz")
    update_global_model(JOB_ID, cid)
    return cid

class Strategy(fl.server.strategy.FedAvg):
    def __init__(self):
        super().__init__()
        self.latest_cid = save_and_publish_global(INITIAL_WEIGHTS)

    def configure_fit(self, rnd: int, params, client_manager):
        cfg = {"cid_global": self.latest_cid}
        return super().configure_fit(rnd, params, client_manager)  # Flower cuidará dos clients
    def aggregate_fit(self, rnd, results, failures):
        agg, _ = super().aggregate_fit(rnd, results, failures)
        if agg is not None:
            # 'agg' é um ndarrays- like conforme sua strategy; normalizamos pra lista
            if isinstance(agg, list):
                new_global = agg
            else:
                new_global = list(agg.parameters.tensors)  # fallback
            self.latest_cid = save_and_publish_global(new_global)
        return agg, {}

def main():
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        strategy=Strategy(),
        config=fl.server.ServerConfig(num_rounds=ROUNDS),
    )

if __name__ == "__main__":
    main()