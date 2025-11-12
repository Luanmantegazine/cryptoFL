import os
import flwr as fl
from flwr.common import parameters_to_ndarrays
from onchain_job import job_update_global
from ipfs import ipfs_add_numpy
from utils import ROUNDS, init_weights

JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]

if not JOB_ADDRS:
    raise RuntimeError("Configure JOB_ADDRS com pelo menos um endereço de JobContract (execute o main.py primeiro)")


class Strategy(fl.server.strategy.FedAvg):
    def __init__(self):
        super().__init__()

        print("[On-chain] Criando modelo inicial e publicando no IPFS...")
        self.latest_cid = ipfs_add_numpy(init_weights(), "global_round0.npz")
        print(f"[On-chain] Modelo inicial (Round 0) no IPFS: {self.latest_cid}")

        for addr in JOB_ADDRS:
            r = job_update_global(addr, self.latest_cid)
            print(f"[JOB {addr}] UpdateGlobalModel r0 tx={r['hash']} gas={r['gasETH']:.8f} ETH")

    def configure_fit(self, server_round, parameters, client_manager):
        instructions = super().configure_fit(server_round, parameters, client_manager)
        for _, fit_ins in instructions:
            fit_ins.config.setdefault("cid_global", self.latest_cid)
        return instructions

    def aggregate_fit(self, server_round, results, failures):
        agg, _ = super().aggregate_fit(server_round, results, failures)

        if agg and agg.parameters:
            nds = parameters_to_ndarrays(agg.parameters)

            self.latest_cid = ipfs_add_numpy(nds, f"global_round{server_round}.npz")
            print(f"[On-chain] Modelo agregado (Round {server_round}) no IPFS: {self.latest_cid}")

            for addr in JOB_ADDRS:
                r = job_update_global(addr, self.latest_cid)
                print(f"[JOB {addr}] UpdateGlobalModel r{server_round} tx={r['hash']} gas={r['gasETH']:.8f} ETH")
        return agg, {}


def main():
    print(f"[Flower] Iniciando servidor em 0.0.0.0:8080 | rounds={ROUNDS}")
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        strategy=Strategy(),
        config=fl.server.ServerConfig(num_rounds=ROUNDS),
    )


if __name__ == "__main__":
    main()