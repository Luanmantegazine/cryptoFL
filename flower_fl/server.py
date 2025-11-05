import os
import flwr as fl
from onchain_job import job_update_global
from ipfs import ipfs_add_numpy
from utils import ROUNDS, init_weights

JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]

if not JOB_ADDRS:
    raise RuntimeError("Configure JOB_ADDRS com pelo menos um endereço de JobContract")


class Strategy(fl.server.strategy.FedAvg):
    def __init__(self):
        super().__init__()
        self.latest_cid = ipfs_add_numpy(init_weights(), "global_round0.npz")
        for addr in JOB_ADDRS:
            r = job_update_global(addr, self.latest_cid)
            print(f"[JOB {addr}] UpdateGlobalModel r0 tx={r['hash']} gas={r['gasETH']:.8f} ETH")

    def configure_fit(self, rnd, params, client_manager):
        instructions = super().configure_fit(rnd, params, client_manager)
        for _, fit_ins in instructions:
            fit_ins.config.setdefault("cid_global", self.latest_cid)
        return instructions

    def aggregate_fit(self, rnd, results, failures):
        agg, _ = super().aggregate_fit(rnd, results, failures)
        if agg and agg.parameters:
            nds = fl.common.parameters_to_ndarrays(agg.parameters)
            self.latest_cid = ipfs_add_numpy(nds, f"global_round{rnd}.npz")
            for addr in JOB_ADDRS:
                r = job_update_global(addr, self.latest_cid)
                print(f"[JOB {addr}] UpdateGlobalModel r{rnd} tx={r['hash']} gas={r['gasETH']:.8f} ETH")
        return agg, {}


def main():
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        strategy=Strategy(),
        config=fl.server.ServerConfig(num_rounds=ROUNDS),
    )


if __name__ == "__main__":
    main()
