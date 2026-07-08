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
from .utils import ROUNDS, USE_IPFS, USE_ONCHAIN

# NOTE: `onchain_job` (web3) and `ipfs` (Pinata/requests) are imported lazily
# inside the publish paths below. This lets the baseline / no_ipfs runs import
# and start the server without pulling modules they don't need — only the paths
# guarded by USE_IPFS / USE_ONCHAIN import them.


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
NORM_DETECTOR_MODE = os.getenv("NORM_DETECTOR_MODE", "both").lower()

# Anomaly detector (see aggregate_fit): computes each client's update norm
# ||w_i - w_global||_2 and flags outliers by thresholding around the round mean.
#
# Modes:
# - upper: flags only unusually large norms (norm > mean + k*std)
# - both: flags both high and low outliers (|norm - mean| > k*std)

# USE_IPFS / USE_ONCHAIN (importados de utils) controlam, de forma
# INDEPENDENTE, o armazenamento no IPFS e a ancoragem on-chain. O modo
# `no_ipfs` usa USE_IPFS=false + USE_ONCHAIN=true: os pesos vão pelo
# protocolo Flower e um hash de conteúdo é ancorado on-chain (gás real).
if USE_ONCHAIN and not JOB_ADDRS:
    raise RuntimeError(
        "USE_ONCHAIN=true requer JOB_ADDRS no .env (os modos no_ipfs e full "
        "ancoram on-chain e precisam do Hardhat + contrato deployado). "
        "Para uma run puramente Flower use USE_ONCHAIN=false (ou o baseline_runner)."
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
        matching_time_s=None,
        download_model_time_s=None,
        local_training_time_s=None,
        upload_ipfs_time_s=None,
        blockchain_tx_time_s=None,
        publish_global_model_time_s=None,
        round_total_time_s=None,
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
            "matching_time_s": matching_time_s,
            "download_model_time_s": download_model_time_s,
            "local_training_time_s": local_training_time_s,
            "upload_ipfs_time_s": upload_ipfs_time_s,
            "blockchain_tx_time_s": blockchain_tx_time_s,
            "publish_global_model_time_s": publish_global_model_time_s,
            "round_total_time_s": round_total_time_s,
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
        self.current_global_ndarrays = None
        self._matching_time_by_round = {}
        self._initialize_global_model()
        if NORM_DETECTOR_MODE not in {"upper", "both"}:
            print(f"[WARN] NORM_DETECTOR_MODE inválido: {NORM_DETECTOR_MODE!r}; usando 'both'")
            self.norm_detector_mode = "both"
        else:
            self.norm_detector_mode = NORM_DETECTOR_MODE
        print(
            "[Detector] detect_anomalies="
            f"{DETECT_ANOMALIES} mode={self.norm_detector_mode} "
            f"k={NORM_THRESHOLD_STD:.2f}"
        )
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
            self.current_global_ndarrays = initial_params
            print(f" ✓ {len(initial_params)} camadas")

            # [2/3] Camada de ARMAZENAMENTO (IPFS) — opcional (USE_IPFS).
            content_ref = None
            if USE_IPFS:
                from .ipfs import ipfs_add_numpy
                print("[2/3] Publicando no IPFS...")
                self.latest_cid = ipfs_add_numpy(initial_params, "global_round0.npz")
                content_ref = self.latest_cid
                print(f" ✓ CID: {self.latest_cid}")
            else:
                # Sem IPFS: os pesos trafegam via protocolo Flower. Para ancorar
                # on-chain usamos um hash de conteúdo determinístico dos pesos.
                self.latest_cid = None
                if USE_ONCHAIN:
                    from .ipfs import content_hash_numpy
                    content_ref = content_hash_numpy(initial_params)
                    print(f"[2/3] Sem IPFS: hash de conteúdo p/ ancoragem = {content_ref[:24]}...")
                else:
                    print("[2/3] Sem IPFS e sem on-chain (Flower puro)")

            # [3/3] Camada de ANCORAGEM (on-chain) — opcional (USE_ONCHAIN).
            if USE_ONCHAIN:
                from .onchain_job import job_update_global
                print("[3/3] Registrando on-chain...")
                for idx, addr in enumerate(JOB_ADDRS, 1):
                    _t0 = time.time()
                    result = job_update_global(addr, content_ref)
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
                print("\n Modelo inicial publicado (on-chain)!\n")
            else:
                self.metrics.log_round(0, 0.0, None, None, 0, 0, tx_latency_s=None)
                print("\n Modelo inicial pronto (Flower puro)!\n")

        except Exception as e:
            print(f"\n ERRO: {e}")
            sys.exit(1)

    # -------------------------
    # Injeta CID global nos clientes
    # -------------------------
    def configure_fit(self, server_round, parameters, client_manager):
        _match_t0 = time.time()
        instructions = super().configure_fit(server_round, parameters, client_manager)
        for _, fit_ins in instructions:
            if USE_IPFS and self.latest_cid is not None:
                fit_ins.config.setdefault("cid_global", self.latest_cid)
            fit_ins.config.setdefault("epochs", 1)
            fit_ins.config.setdefault("server_round", server_round)
        self._matching_time_by_round[server_round] = time.time() - _match_t0
        return instructions

    # -------------------------
    # Agregação + salvamento de métricas
    # -------------------------
    def aggregate_fit(self, server_round, results, failures):
        print(f"\n{'=' * 70}")
        print(f" ROUND {server_round}/{ROUNDS}")
        print(f"{'=' * 70}")

        import numpy as np
        round_stage_times = {
            "matching_time_s": self._matching_time_by_round.pop(server_round, 0.0),
            "download_model_time_s": 0.0,
            "local_training_time_s": 0.0,
            "upload_ipfs_time_s": 0.0,
            "blockchain_tx_time_s": 0.0,
            "aggregation_time_s": 0.0,
            "publish_global_model_time_s": 0.0,
            "round_total_time_s": 0.0,
        }

        # Snapshot do global atual (rodada anterior). Usado para medir norma
        # de UPDATE: ||w_i - w_global||_2.
        global_flat = None
        has_global_for_detection = False
        if self.current_global_ndarrays is not None:
            try:
                if len(self.current_global_ndarrays) > 0:
                    global_flat = np.concatenate(
                        [p.flatten() for p in self.current_global_ndarrays]
                    )
                    has_global_for_detection = global_flat.size > 0
            except Exception as e:
                print(f"[WARN] não foi possível materializar w_global: {e}")
                has_global_for_detection = False

        # 1. Calcular norma L2 de UPDATE de cada cliente e coletar métricas.
        norms = []
        client_metrics = []
        for idx, (client, fit_res) in enumerate(results, start=1):
            try:
                params = fl.common.parameters_to_ndarrays(fit_res.parameters)
                flat = np.concatenate([p.flatten() for p in params])
                if has_global_for_detection:
                    if flat.shape != global_flat.shape:
                        raise ValueError(
                            f"shape incompatível: cliente={flat.shape}, global={global_flat.shape}"
                        )
                    flat = flat - global_flat
                    norm = float(np.linalg.norm(flat))
                else:
                    norm = float("nan")
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

        # 2. Detecção de anomalias por norma de update.
        valid_norms = [n for n in norms if not (n != n)]  # filtra NaN
        mean_norm = float(np.mean(valid_norms)) if valid_norms else None
        std_norm = float(np.std(valid_norms)) if len(valid_norms) > 1 else 0.0
        n_flagged = 0
        if DETECT_ANOMALIES and not has_global_for_detection:
            print(
                f"[Detector] Round {server_round}: w_global indisponível; "
                "detecção inicia quando houver modelo global anterior (esperado: round 2)."
            )
        if DETECT_ANOMALIES and mean_norm is not None and has_global_for_detection:
            threshold = mean_norm + NORM_THRESHOLD_STD * std_norm
            lower_threshold = mean_norm - NORM_THRESHOLD_STD * std_norm
            for entry, n in zip(client_metrics, norms):
                flagged = False
                if n == n:  # n == n filtra NaN
                    if self.norm_detector_mode == "upper":
                        flagged = n > threshold
                    else:  # both
                        flagged = abs(n - mean_norm) > (NORM_THRESHOLD_STD * std_norm)
                entry["flagged_as_suspicious"] = int(flagged)
                print(
                    f"[Detector] round={server_round} client={entry.get('node_id', entry.get('client_index'))} "
                    f"update_norm={n:.6f} mean={mean_norm:.6f} std={std_norm:.6f} "
                    f"tau_upper={threshold:.6f} tau_lower={lower_threshold:.6f} "
                    f"mode={self.norm_detector_mode} flagged={flagged}"
                )
                if flagged:
                    entry["flagged_as_suspicious"] = 1
                    n_flagged += 1
            if n_flagged > 0:
                print(
                    f"[Servidor] ⚠ Round {server_round}: {n_flagged}/{len(results)} "
                    f"updates suspeitos (modo={self.norm_detector_mode})"
                )

        # train_time_round_s = tempo de treino do round. Como os clientes
        # treinam EM PARALELO, o tempo de parede do round é ~max(train_time).
        client_train_times = [
            float(c.get("train_time", 0.0)) for c in client_metrics
            if c.get("train_time") is not None
        ]
        train_time_round_s = max(client_train_times) if client_train_times else None

        def _max_client_metric(key: str) -> float:
            vals = []
            for c in client_metrics:
                v = c.get(key)
                if v is None:
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            return max(vals) if vals else 0.0

        round_stage_times["download_model_time_s"] = _max_client_metric("download_time_s")
        round_stage_times["local_training_time_s"] = (
            float(train_time_round_s) if train_time_round_s is not None else 0.0
        )
        round_stage_times["upload_ipfs_time_s"] = _max_client_metric("upload_ipfs_time_s")
        round_stage_times["blockchain_tx_time_s"] = _max_client_metric("blockchain_tx_time_s")

        # 3. Agregar parâmetros (FedAvg pleno — não removemos clientes flagged).
        # aggregate_time_s mede SOMENTE a agregação FedAvg server-side (~0.01s),
        # não o treino dos clientes (ver Tarefa 1.2).
        _agg_t0 = time.time()
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )
        aggregate_time_s = time.time() - _agg_t0
        round_stage_times["aggregation_time_s"] = float(aggregate_time_s)

        accuracy = None
        if aggregated_metrics and "accuracy" in aggregated_metrics:
            accuracy = aggregated_metrics["accuracy"]

        if aggregated_parameters is None:
            print(" Nenhum parâmetro agregado")
            return None, {}

        # 3. Salvar modelo, ancorar on-chain, salvar métricas
        try:
            aggregated_ndarrays = parameters_to_ndarrays(aggregated_parameters)
            self.current_global_ndarrays = aggregated_ndarrays
            _publish_t0 = time.time()

            # Camada de ARMAZENAMENTO (IPFS) — opcional (USE_IPFS).
            content_ref = None
            if USE_IPFS:
                from .ipfs import ipfs_add_numpy
                print(f"\n[1/2] Publicando no IPFS...")
                self.latest_cid = ipfs_add_numpy(
                    aggregated_ndarrays,
                    f"global_round{server_round}.npz",
                )
                content_ref = self.latest_cid
                print(f" ✓ CID: {self.latest_cid}")
            else:
                # Sem IPFS: pesos via Flower; ancora um hash de conteúdo.
                self.latest_cid = None
                if USE_ONCHAIN:
                    from .ipfs import content_hash_numpy
                    content_ref = content_hash_numpy(aggregated_ndarrays)

            # Camada de ANCORAGEM (on-chain) — opcional (USE_ONCHAIN).
            round_gas_eth = 0.0
            round_tx = None
            round_lat = None
            if USE_ONCHAIN:
                from .onchain_job import job_update_global
                print(f"[2/2] Registrando on-chain...")
                for idx, addr in enumerate(JOB_ADDRS, 1):
                    _t0 = time.time()
                    result = job_update_global(addr, content_ref)
                    _lat = time.time() - _t0

                    self.metrics.metrics["gas_breakdown"].append({
                        "round": server_round,
                        "operation": "publish_global_model",
                        "gas_eth": result["gasETH"],
                        "tx_hash": result["hash"],
                    })
                    if idx == 1:  # gás do round = primeira ancoragem
                        round_gas_eth = result["gasETH"]
                        round_tx = result["hash"]
                        round_lat = _lat

            round_stage_times["publish_global_model_time_s"] = time.time() - _publish_t0
            round_stage_times["round_total_time_s"] = (
                round_stage_times["matching_time_s"]
                + round_stage_times["download_model_time_s"]
                + round_stage_times["local_training_time_s"]
                + round_stage_times["upload_ipfs_time_s"]
                + round_stage_times["blockchain_tx_time_s"]
                + round_stage_times["aggregation_time_s"]
                + round_stage_times["publish_global_model_time_s"]
            )
            _total = round_stage_times["round_total_time_s"]
            if _total > 0:
                print("[Tempo do round] "
                      f"train={100.0 * round_stage_times['local_training_time_s'] / _total:.1f}% | "
                      f"upload={100.0 * round_stage_times['upload_ipfs_time_s'] / _total:.1f}% | "
                      f"blockchain={100.0 * round_stage_times['blockchain_tx_time_s'] / _total:.1f}% | "
                      f"matching={100.0 * round_stage_times['matching_time_s'] / _total:.1f}% | "
                      f"agg={100.0 * round_stage_times['aggregation_time_s'] / _total:.1f}% | "
                      f"pub={100.0 * round_stage_times['publish_global_model_time_s'] / _total:.1f}%")

            self.metrics.log_round(
                server_round,
                round_gas_eth,
                self.latest_cid,
                round_tx,
                len(results),
                len(failures),
                accuracy,
                client_metrics=client_metrics,
                aggregated_metrics=aggregated_metrics,
                tx_latency_s=round_lat,
                mean_update_norm=mean_norm,
                std_update_norm=std_norm,
                n_flagged=n_flagged,
                aggregate_time_s=aggregate_time_s,
                train_time_round_s=train_time_round_s,
                matching_time_s=round_stage_times["matching_time_s"],
                download_model_time_s=round_stage_times["download_model_time_s"],
                local_training_time_s=round_stage_times["local_training_time_s"],
                upload_ipfs_time_s=round_stage_times["upload_ipfs_time_s"],
                blockchain_tx_time_s=round_stage_times["blockchain_tx_time_s"],
                publish_global_model_time_s=round_stage_times["publish_global_model_time_s"],
                round_total_time_s=round_stage_times["round_total_time_s"],
            )

            _mode = ("full" if USE_IPFS and USE_ONCHAIN else
                     "no_ipfs" if USE_ONCHAIN else "flower")
            print(f"\n Round {server_round} concluído ({_mode})!")

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

    _seed = os.getenv("SEED")
    if _seed is not None:
        try:
            from .utils import set_seed
            set_seed(int(_seed))
            print(f" SEED={_seed}")
        except ValueError:
            pass

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
