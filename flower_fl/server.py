import os

os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import sys
import json
from datetime import datetime
from pathlib import Path

import flwr as fl
from flwr.common import parameters_to_ndarrays

from models import MNISTNet
from onchain_job import job_update_global
from ipfs import ipfs_add_numpy
from utils import ROUNDS


# ==============================
# Configurações
# ==============================
JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]
SAVE_METRICS = os.getenv("SAVE_METRICS", "true").lower() == "true"
METRICS_FILE = os.getenv("METRICS_FILE", "results/server_metrics.json")

if not JOB_ADDRS:
    raise RuntimeError("Configure JOB_ADDRS no .env")


# ==============================
# Coletor de Métricas
# ==============================
class MetricsCollector:
    def __init__(self, job_addrs):
        self.metrics = {
            "experiment_start": datetime.now().isoformat(),
            "job_addresses": job_addrs,
            "total_rounds": ROUNDS,
            "rounds": [],
            "total_gas_eth": 0.0,
            "final_accuracy": 0.0,
            "accuracy_history": [],
        }

    def log_round(
        self,
        round_num,
        gas_fee,
        cid,
        tx_hash,
        num_clients,
        failures,
        accuracy=None,
        client_metrics=None,
        aggregated_metrics=None,
    ):
        round_data = {
            "round": round_num,
            "timestamp": datetime.now().isoformat(),
            "num_clients": num_clients,
            "num_failures": failures,
            "gas_eth": gas_fee,
            "tx_hash": tx_hash,
            "ipfs_cid": cid,
        }

        if accuracy is not None:
            round_data["accuracy"] = accuracy
            self.metrics["accuracy_history"].append(accuracy)
            self.metrics["final_accuracy"] = accuracy

        if client_metrics is not None:
            round_data["client_metrics"] = client_metrics

        if aggregated_metrics is not None:
            round_data["aggregated_metrics"] = aggregated_metrics

        self.metrics["rounds"].append(round_data)
        self.metrics["total_gas_eth"] += gas_fee

    def save(self):
        if not SAVE_METRICS:
            return

        self.metrics["experiment_end"] = datetime.now().isoformat()
        Path(METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)

        with open(METRICS_FILE, "w") as f:
            json.dump(self.metrics, f, indent=2)

        print(f"\n Métricas salvas em: {METRICS_FILE}")
        print(f" Gas total: {self.metrics['total_gas_eth']:.8f} ETH")


# ==============================
# Estratégia de aprendizado
# ==============================
class BlockchainFLStrategy(fl.server.strategy.FedAvg):

    @staticmethod
    def _aggregate_metrics(metrics):
        if not metrics:
            return {}

        total_examples = sum(num_examples for num_examples, _ in metrics)
        if total_examples == 0:
            return {}

        total_accuracy = 0.0
        total_loss = 0.0
        acc_count = 0
        loss_count = 0

        for num_examples, client_metrics in metrics:
            if "accuracy" in client_metrics:
                total_accuracy += client_metrics["accuracy"] * num_examples
                acc_count += num_examples
            if "loss" in client_metrics:
                total_loss += client_metrics["loss"] * num_examples
                loss_count += num_examples
            elif "avg_loss" in client_metrics:
                total_loss += client_metrics["avg_loss"] * num_examples
                loss_count += num_examples

        aggregated = {}
        if acc_count:
            aggregated["accuracy"] = total_accuracy / acc_count
        if loss_count:
            aggregated["loss"] = total_loss / loss_count

        return aggregated

    def __init__(self, min_clients=3):
        super().__init__(
            fraction_fit=1.0,
            fraction_evaluate=0.0,
            min_fit_clients=min_clients,
            min_evaluate_clients=min_clients,
            min_available_clients=min_clients,
            fit_metrics_aggregation_fn=self._aggregate_metrics,
        )

        self.metrics = MetricsCollector(JOB_ADDRS)
        self.latest_cid = None
        self._initialize_global_model()

    # -------------------------
    # Inicializar modelo global
    # -------------------------
    def _initialize_global_model(self):
        print("\n" + "=" * 70)
        print(" INICIALIZANDO MODELO GLOBAL")
        print("=" * 70)

        try:
            print("[1/3] Criando MNISTNet...")
            model = MNISTNet()
            initial_params = [val.cpu().numpy() for _, val in model.state_dict().items()]
            print(f" ✓ {len(initial_params)} camadas")

            print("[2/3] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(initial_params, "global_round0.npz")
            print(f" ✓ CID: {self.latest_cid}")

            print("[3/3] Registrando on-chain...")
            for idx, addr in enumerate(JOB_ADDRS, 1):
                result = job_update_global(addr, self.latest_cid)
                print(f" ✓ Job {idx}: {addr[:10]}...")
                print(f"   Tx: {result['hash']}")
                print(f"   Gas: {result['gasETH']:.8f} ETH")

                self.metrics.log_round(
                    0,
                    result["gasETH"],
                    self.latest_cid,
                    result["hash"],
                    0,
                    0,
                )

            print("\n Modelo inicial publicado!\n")

        except Exception as e:
            print(f"\n ERRO: {e}")
            sys.exit(1)

    # -------------------------
    # Injeta CID global nos clientes
    # -------------------------
    def configure_fit(self, server_round, parameters, client_manager):
        instructions = super().configure_fit(server_round, parameters, client_manager)
        for _, fit_ins in instructions:
            fit_ins.config.setdefault("cid_global", self.latest_cid)
            fit_ins.config.setdefault("epochs", 1)
            fit_ins.config.setdefault("server_round", server_round)
        return instructions

    # -------------------------
    # Agregação + salvamento de métricas
    # -------------------------
    def aggregate_fit(self, server_round, results, failures):
        print(f"\n{'=' * 70}")
        print(f" ROUND {server_round}/{ROUNDS}")
        print(f"{'=' * 70}")

        # 1. Coletar métricas individuais dos clientes
        client_metrics = []
        for idx, (client, fit_res) in enumerate(results, start=1):
            m = fit_res.metrics or {}
            entry = {
                "client_index": idx,
                "num_examples": fit_res.num_examples,
            }
            entry.update(m)
            client_metrics.append(entry)

        # 2. Agregar parâmetros
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )

        accuracy = None
        if aggregated_metrics and "accuracy" in aggregated_metrics:
            accuracy = aggregated_metrics["accuracy"]

        if aggregated_parameters is None:
            print(" Nenhum parâmetro agregado")
            return None, {}

        # 3. Salvar modelo, registrar no blockchain, salvar métricas
        try:
            aggregated_ndarrays = parameters_to_ndarrays(aggregated_parameters)

            # IPFS
            print(f"\n[1/2] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(
                aggregated_ndarrays,
                f"global_round{server_round}.npz"
            )

            print(f" ✓ CID: {self.latest_cid}")

            # Blockchain
            print(f"[2/2] Registrando on-chain...")
            for idx, addr in enumerate(JOB_ADDRS, 1):
                result = job_update_global(addr, self.latest_cid)

                if idx == 1:  # registra uma vez
                    self.metrics.log_round(
                        server_round,
                        result["gasETH"],
                        self.latest_cid,
                        result["hash"],
                        len(results),
                        len(failures),
                        accuracy,
                        client_metrics=client_metrics,
                        aggregated_metrics=aggregated_metrics,
                    )

            print(f"\n Round {server_round} concluído!")

        except Exception as e:
            print(f"\n ERRO: {e}")

        return aggregated_parameters, aggregated_metrics


# ==============================
# Main
# ==============================
def main():
    print("\n" + "=" * 70)
    print(" FLOWER FEDERATED LEARNING SERVER")
    print("=" * 70)

    min_clients = int(os.getenv("MIN_CLIENTS", "1"))
    strategy = BlockchainFLStrategy(min_clients=min_clients)

    config = fl.server.ServerConfig(num_rounds=ROUNDS, round_timeout=None)

    try:
        fl.server.start_server(
            server_address="0.0.0.0:8080",
            strategy=strategy,
            config=config,
            grpc_max_message_length=536870912,
        )

        strategy.metrics.save()

    except Exception as e:
        print(f"\n ERRO FATAL: {e}")
        strategy.metrics.save()
        sys.exit(1)


if __name__ == "__main__":
    main()
