import os
import flwr as fl
from flwr.common import parameters_to_ndarrays
from onchain_job import job_update_global
from ipfs import ipfs_add_numpy
from utils import ROUNDS
from models import MNISTNet

JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]

if not JOB_ADDRS:
    raise RuntimeError("Configure JOB_ADDRS com pelo menos um endereço de JobContract (execute o main.py primeiro)")


def get_initial_parameters():
    model = MNISTNet()
    return [val.cpu().numpy() for _, val in model.state_dict().items()]


class Strategy(fl.server.strategy.FedAvg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        print("[On-chain] Criando modelo inicial MNISTNet e publicando no IPFS...")
        initial_weights = get_initial_parameters()
        self.latest_cid = ipfs_add_numpy(initial_weights, "global_round0.npz")
        print(f"[On-chain] Modelo inicial (Round 0) no IPFS: {self.latest_cid}")

        for addr in JOB_ADDRS:
            r = job_update_global(addr, self.latest_cid)
            print(f"[JOB {addr}] UpdateGlobalModel r0 tx={r['hash']} gas={r['gasETH']:.8f} ETH")

    def configure_fit(self, rnd, params, client_manager):
        instructions = super().configure_fit(rnd, params, client_manager)
        for _, fit_ins in instructions:
            fit_ins.config.setdefault("cid_global", self.latest_cid)
            fit_ins.config.setdefault("epochs", 1)
        return instructions

    def aggregate_fit(self, rnd, results, failures):
        agg, _ = super().aggregate_fit(rnd, results, failures)

        if agg and agg.parameters:
            nds = parameters_to_ndarrays(agg.parameters)

            self.latest_cid = ipfs_add_numpy(nds, f"global_round{rnd}.npz")
            print(f"[On-chain] Modelo agregado (Round {rnd}) no IPFS: {self.latest_cid}")

            for addr in JOB_ADDRS:
                r = job_update_global(addr, self.latest_cid)
                print(f"[JOB {addr}] UpdateGlobalModel r{rnd} tx={r['hash']} gas={r['gasETH']:.8f} ETH")
        return agg, {}


def main():
    print(f"[Flower] Iniciando servidor em 0.0.0.0:8080 | rounds={ROUNDS}")

    base_strategy = fl.server.strategy.FedAvg()

    strategy_wrapper = Strategy(
        fraction_fit=1.0,  # Treinar em 100% dos clientes disponíveis
        fraction_evaluate=1.0,  # Avaliar em 100%
        min_fit_clients=len(JOB_ADDRS),  # Esperar todos os clientes
        min_available_clients=len(JOB_ADDRS),
    )

    fl.server.start_server(
        server_address="0.0.0.0:8080",
        strategy=strategy_wrapper,
        config=fl.server.ServerConfig(num_rounds=ROUNDS),
    )


if __name__ == "__main__":
    main()
