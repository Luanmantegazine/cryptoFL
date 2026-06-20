import os
import time

os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import sys
import json
from datetime import datetime
from pathlib import Path

import flwr as fl
from flwr.common import parameters_to_ndarrays

from .models import MNISTNet, get_model
from .utils import ROUNDS

# NOTE: `onchain_job` (web3) and `ipfs` (Pinata/requests) are imported lazily
# inside the publish paths below. This lets the SKIP_IPFS / no_ipfs / baseline
# runs import and start the server WITHOUT an RPC endpoint, a private key, or a
# Pinata JWT — only the `full` on-chain flow pulls those modules in.


# ==============================
# Configurações
# ==============================
JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]
SAVE_METRICS = os.getenv("SAVE_METRICS", "true").lower() == "true"
METRICS_FILE = os.getenv("METRICS_FILE", "results/server_metrics.json")
DATASET_NAME = os.getenv("DATASET", "mnist")
MODEL_NAME = os.getenv("MODEL", "mnistnet")
DETECT_ANOMALIES = os.getenv("DETECT_ANOMALIES", "true").lower() == "true"
NORM_THRESHOLD_STD = float(os.getenv("NORM_THRESHOLD_STD", "2.0"))
# Anomaly detector (see aggregate_fit): flags updates whose L2 norm exceeds
# mean + NORM_THRESHOLD_STD*std across a round.
#
# SCOPE / THREAT MODEL: this heuristic targets NORM-INFLATING attacks — i.e.
# `noise` (random images blow up gradients/weights) and `zero` — where a
# poisoned update has an anomalously large L2 norm. It is ORTHOGONAL to
# `label_flip`: flipping labels produces a perfectly normal-magnitude update,
# so the norm check cannot (and does not) flag it. To get a non-zero
# `n_flagged_total` in security experiments, use --attack-type noise. Defending
# label-flipping requires a different signal (e.g. validation accuracy, update
# direction / cosine, or robust aggregation), which is left as future work.
SKIP_IPFS = os.getenv("SKIP_IPFS", "false").lower() == "true"
# Quando True, não publica no IPFS nem on-chain (modo `no_ipfs` da ablação).

if not SKIP_IPFS and not JOB_ADDRS:
    raise RuntimeError(
        "Configure JOB_ADDRS no .env (ou rode com SKIP_IPFS=true para o modo no_ipfs)."
    )


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
            "gas_breakdown": [],
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
        tx_latency_s=None,
        mean_update_norm=None,
        std_update_norm=None,
        n_flagged=None,
        aggregate_time_s=None,
        train_time_round_s=None,
    ):
        round_data = {
            "round": round_num,
            "timestamp": datetime.now().isoformat(),
            "num_clients": num_clients,
            "num_failures": failures,
            "gas_eth": gas_fee,
            "tx_hash": tx_hash,
            "ipfs_cid": cid,
            "tx_latency_s": tx_latency_s,
            "mean_update_norm": mean_update_norm,
            "std_update_norm": std_update_norm,
            "n_flagged": n_flagged,
            # Tempos separados (ver Tarefa 1.2): aggregate_time_s mede só a
            # agregação FedAvg no servidor (~0.01s); train_time_round_s é o
            # tempo de treino do round = max(train_time dos clientes), pois os
            # clientes treinam em paralelo.
            "aggregate_time_s": aggregate_time_s,
            "train_time_round_s": train_time_round_s,
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

        # Breakdown separado em <metrics>_breakdown.json (default:
        # results/server_metrics_breakdown.json).
        metrics_path = Path(METRICS_FILE)
        breakdown_file = str(
            metrics_path.with_name(metrics_path.stem + "_breakdown" + metrics_path.suffix)
        )
        with open(breakdown_file, "w") as f:
            json.dump(self.metrics["gas_breakdown"], f, indent=2)

        print(f"\n Métricas salvas em: {METRICS_FILE}")
        print(f" Gas breakdown em : {breakdown_file}")
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
        """Inicializa a estratégia FedAvg com camada blockchain.

        Notas sobre sincronização inicial: `min_fit_clients` já mitiga
        parcialmente o problema de clientes ainda não conectados no round 1,
        mas não é uma garantia. Um heartbeat explícito cliente→servidor
        seria necessário para eliminar a janela de corrida (ver Tarefa 4
        do Sprint 1). O `time.sleep(5)` abaixo está disponível como
        mitigação adicional caso o handshake gRPC demore.
        """
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
        # NOTE: min_fit_clients already prevents rounds from starting before enough
        # clients connect. A heartbeat/readiness endpoint would fully eliminate the
        # first-round participation bug (see Section 4.1 of the paper).

    # -------------------------
    # Inicializar modelo global
    # -------------------------
    def _initialize_global_model(self):
        print("\n" + "=" * 70)
        print(" INICIALIZANDO MODELO GLOBAL")
        print("=" * 70)

        try:
            print(f"[1/3] Criando modelo: {MODEL_NAME}")
            model = get_model(MODEL_NAME)
            initial_params = [val.cpu().numpy() for _, val in model.state_dict().items()]
            print(f" ✓ {len(initial_params)} camadas")

            if SKIP_IPFS:
                print("[2/3] SKIP_IPFS: pulando publicação no IPFS")
                self.latest_cid = None
                print("[3/3] SKIP_IPFS: pulando registro on-chain")
                self.metrics.log_round(
                    0,
                    0.0,
                    None,
                    None,
                    0,
                    0,
                    tx_latency_s=None,
                )
                print("\n Modelo inicial pronto (sem IPFS/blockchain)!\n")
                return

            # Imports tardios: só o fluxo `full` (com IPFS + on-chain) os carrega.
            from .ipfs import ipfs_add_numpy
            from .onchain_job import job_update_global

            print("[2/3] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(initial_params, "global_round0.npz")
            print(f" ✓ CID: {self.latest_cid}")

            print("[3/3] Registrando on-chain...")
            for idx, addr in enumerate(JOB_ADDRS, 1):
                _t0 = time.time()
                result = job_update_global(addr, self.latest_cid)
                _lat = time.time() - _t0
                print(f" ✓ Job {idx}: {addr[:10]}...")
                print(f"   Tx: {result['hash']}")
                print(f"   Gas: {result['gasETH']:.8f} ETH  Lat: {_lat:.3f}s")

                self.metrics.metrics["gas_breakdown"].append({
                    "round": 0,
                    "operation": "publish_global_model",
                    "gas_eth": result["gasETH"],
                    "tx_hash": result["hash"],
                })

                self.metrics.log_round(
                    0,
                    result["gasETH"],
                    self.latest_cid,
                    result["hash"],
                    0,
                    0,
                    tx_latency_s=_lat,
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
            if not SKIP_IPFS:
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

        import numpy as np

        # 1. Calcular norma L2 de cada update e coletar métricas dos clientes.
        norms = []
        client_metrics = []
        for idx, (client, fit_res) in enumerate(results, start=1):
            try:
                params = fl.common.parameters_to_ndarrays(fit_res.parameters)
                flat = np.concatenate([p.flatten() for p in params])
                norm = float(np.linalg.norm(flat))
            except Exception as e:
                print(f" [WARN] norma indisponível para cliente {idx}: {e}")
                norm = float("nan")
            norms.append(norm)

            m = dict(fit_res.metrics or {})
            m["update_norm"] = norm
            entry = {
                "client_index": idx,
                "num_examples": fit_res.num_examples,
            }
            entry.update(m)
            client_metrics.append(entry)

        # 2. Detecção de anomalias por norma (mean + N*std).
        valid_norms = [n for n in norms if not (n != n)]  # filtra NaN
        mean_norm = float(np.mean(valid_norms)) if valid_norms else None
        std_norm = float(np.std(valid_norms)) if len(valid_norms) > 1 else 0.0
        n_flagged = 0
        if DETECT_ANOMALIES and mean_norm is not None:
            threshold = mean_norm + NORM_THRESHOLD_STD * std_norm
            for entry, n in zip(client_metrics, norms):
                if n == n and n > threshold:  # n == n filtra NaN
                    entry["flagged_as_suspicious"] = 1
                    n_flagged += 1
            if n_flagged > 0:
                print(f"[Servidor] ⚠ Round {server_round}: {n_flagged}/{len(results)} updates suspeitos (normas acima de {threshold:.2f})")

        # train_time_round_s = tempo de treino do round. Como os clientes
        # treinam EM PARALELO, o tempo de parede do round é ~max(train_time).
        client_train_times = [
            float(c.get("train_time", 0.0)) for c in client_metrics
            if c.get("train_time") is not None
        ]
        train_time_round_s = max(client_train_times) if client_train_times else None

        # 3. Agregar parâmetros (FedAvg pleno — não removemos clientes flagged).
        # aggregate_time_s mede SOMENTE a agregação FedAvg server-side (~0.01s),
        # não o treino dos clientes (ver Tarefa 1.2).
        _agg_t0 = time.time()
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )
        aggregate_time_s = time.time() - _agg_t0

        accuracy = None
        if aggregated_metrics and "accuracy" in aggregated_metrics:
            accuracy = aggregated_metrics["accuracy"]

        if aggregated_parameters is None:
            print(" Nenhum parâmetro agregado")
            return None, {}

        # 3. Salvar modelo, registrar no blockchain, salvar métricas
        try:
            aggregated_ndarrays = parameters_to_ndarrays(aggregated_parameters)

            if SKIP_IPFS:
                self.latest_cid = None
                self.metrics.log_round(
                    server_round,
                    0.0,
                    None,
                    None,
                    len(results),
                    len(failures),
                    accuracy,
                    client_metrics=client_metrics,
                    aggregated_metrics=aggregated_metrics,
                    tx_latency_s=None,
                    mean_update_norm=mean_norm,
                    std_update_norm=std_norm,
                    n_flagged=n_flagged,
                    aggregate_time_s=aggregate_time_s,
                    train_time_round_s=train_time_round_s,
                )
                print(f"\n Round {server_round} concluído (SKIP_IPFS)!")
                return aggregated_parameters, aggregated_metrics

            # Import tardio: só o fluxo `full` carrega IPFS + on-chain.
            from .ipfs import ipfs_add_numpy
            from .onchain_job import job_update_global

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
                _t0 = time.time()
                result = job_update_global(addr, self.latest_cid)
                _lat = time.time() - _t0

                self.metrics.metrics["gas_breakdown"].append({
                    "round": server_round,
                    "operation": "publish_global_model",
                    "gas_eth": result["gasETH"],
                    "tx_hash": result["hash"],
                })

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
                        tx_latency_s=_lat,
                        mean_update_norm=mean_norm,
                        std_update_norm=std_norm,
                        n_flagged=n_flagged,
                        aggregate_time_s=aggregate_time_s,
                        train_time_round_s=train_time_round_s,
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
