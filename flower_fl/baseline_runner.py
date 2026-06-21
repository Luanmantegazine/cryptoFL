"""Baseline runner: Federated Learning com Flower puro (FedAvg), sem blockchain/IPFS.

Este módulo executa um experimento de FL apenas com o Flower, sem qualquer
chamada para `onchain_job.py` ou `ipfs.py`. Serve como referência de
comparação contra `flower_fl/server.py` (sistema completo) para medir o
overhead introduzido pela camada blockchain.

Saída: arquivo JSON com o mesmo schema de `server_metrics.json`, porém com
`job_addresses=[]`, `total_gas_eth=0.0` e `gas_eth/tx_hash/ipfs_cid=null`
em cada round. Adiciona `train_time_total_s` por round.

Modos de execução (controlados por variáveis de ambiente):
- Default: servidor (porta 8081).
- `BASELINE_AS_CLIENT=1`: cliente baseline (conecta em 8081 sem blockchain).

Exemplo:
    ROUNDS=5 MIN_CLIENTS=3 python -m flower_fl.baseline_runner
"""
import os

# Evita falha do `assert JOB_ADDR` em client.py ao importar (não chamamos blockchain).
os.environ.setdefault("JOB_ADDR", "0x0000000000000000000000000000000000000000")
os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import sys
import json
import time
from datetime import datetime
from pathlib import Path

import flwr as fl

from .models import MNISTNet  # noqa: F401  (mantido para paralelo com server.py)
from .datasets import load_mnist  # noqa: F401
from .client import MNISTClient


ROUNDS = int(os.getenv("ROUNDS", "3"))
MIN_CLIENTS = int(os.getenv("MIN_CLIENTS", "3"))
METRICS_FILE = os.getenv("BASELINE_METRICS_FILE", "results/baseline_metrics.json")
SAVE_METRICS = os.getenv("SAVE_METRICS", "true").lower() == "true"
SERVER_ADDRESS = os.getenv("BASELINE_SERVER_ADDRESS", "0.0.0.0:8081")

# Agregador: "fedavg" (padrão) ou "fedprox". O FedProx usa a MESMA agregação
# ponderada do FedAvg no servidor; a diferença está no cliente, que adiciona o
# termo proximal (mu/2)*||w - w_global||^2 à perda local (Li et al., 2020).
AGGREGATOR = os.getenv("AGGREGATOR", "fedavg").lower()
FEDPROX_MU = float(os.getenv("FEDPROX_MU", "0.1"))

# Timeout (em segundos) por round no servidor. None = espera infinita (o
# comportamento original). O scaling_experiment passa um valor finito via a env
# var ROUND_TIMEOUT para que um cliente morto não trave o sweep inteiro.
ROUND_TIMEOUT = os.getenv("ROUND_TIMEOUT")
_round_timeout = float(ROUND_TIMEOUT) if ROUND_TIMEOUT else None


class BaselineMetricsCollector:
    def __init__(self):
        self.metrics = {
            "experiment_start": datetime.now().isoformat(),
            "job_addresses": [],
            "total_rounds": ROUNDS,
            "rounds": [],
            "total_gas_eth": 0.0,
            "final_accuracy": 0.0,
            "accuracy_history": [],
        }

    def log_round(
        self,
        round_num,
        num_clients,
        failures,
        accuracy=None,
        client_metrics=None,
        aggregated_metrics=None,
        aggregate_time_s=None,
        train_time_round_s=None,
    ):
        round_data = {
            "round": round_num,
            "timestamp": datetime.now().isoformat(),
            "num_clients": num_clients,
            "num_failures": failures,
            "gas_eth": None,
            "tx_hash": None,
            "ipfs_cid": None,
            # Ver Tarefa 1.2: aggregate_time_s = só a agregação FedAvg (~0.01s);
            # train_time_round_s = tempo de treino do round = max(train_time
            # dos clientes), pois treinam em paralelo.
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

    def save(self):
        if not SAVE_METRICS:
            return

        self.metrics["experiment_end"] = datetime.now().isoformat()
        Path(METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_FILE, "w") as f:
            json.dump(self.metrics, f, indent=2)

        print(f"\n Métricas baseline salvas em: {METRICS_FILE}")


class BaselineFLStrategy(fl.server.strategy.FedAvg):
    """Estratégia FedAvg pura, sem chamadas a blockchain/IPFS."""

    @staticmethod
    def _aggregate_metrics(metrics):
        if not metrics:
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
        self.metrics = BaselineMetricsCollector()

    def aggregate_fit(self, server_round, results, failures):
        print(f"\n{'=' * 70}")
        print(f" [BASELINE] ROUND {server_round}/{ROUNDS}")
        print(f"{'=' * 70}")

        client_metrics = []
        for idx, (_, fit_res) in enumerate(results, start=1):
            m = dict(fit_res.metrics or {})
            # remove eventuais campos relacionados a blockchain/ipfs vindos do cliente
            m.pop("cid", None)
            m.pop("tx_hash", None)
            entry = {"client_index": idx, "num_examples": fit_res.num_examples}
            entry.update(m)
            client_metrics.append(entry)

        # train_time_round_s = max(train_time dos clientes) — treinam em paralelo.
        client_train_times = [
            float(c.get("train_time", 0.0)) for c in client_metrics
            if c.get("train_time") is not None
        ]
        train_time_round_s = max(client_train_times) if client_train_times else None

        # aggregate_time_s mede SOMENTE a agregação FedAvg (não o treino).
        agg_start = time.time()
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )
        aggregate_time_s = time.time() - agg_start

        accuracy = None
        if aggregated_metrics and "accuracy" in aggregated_metrics:
            accuracy = aggregated_metrics["accuracy"]

        self.metrics.log_round(
            server_round,
            num_clients=len(results),
            failures=len(failures),
            accuracy=accuracy,
            client_metrics=client_metrics,
            aggregated_metrics=aggregated_metrics,
            aggregate_time_s=aggregate_time_s,
            train_time_round_s=train_time_round_s,
        )

        _ttr = train_time_round_s if train_time_round_s is not None else 0.0
        print(f" [BASELINE] Round {server_round}: train≈{_ttr:.2f}s  "
              f"agg={aggregate_time_s:.3f}s")
        return aggregated_parameters, aggregated_metrics


class BaselineClient(MNISTClient):
    """MNISTClient sem chamadas a IPFS/blockchain.

    Reaproveita o pipeline de treino do `MNISTClient` mas substitui `fit`
    para não publicar pesos no IPFS nem enviar updates on-chain.
    """

    def get_parameters(self, config):
        # Ignora `cid_global` (não baixa nada do IPFS no baseline).
        return [val.cpu().numpy() for _, val in self.model.state_dict().items()]

    def fit(self, parameters, config):
        import torch
        import torch.nn as nn

        self.set_parameters(parameters)

        optimizer = torch.optim.Adam(self.model.parameters())
        criterion = nn.NLLLoss()
        self.model.train()
        self.model.to(self.device)

        server_round = config.get("server_round", "?")
        epochs = int(config.get("epochs", 1))

        # FedProx: guarda uma cópia (congelada) dos pesos globais do início do
        # round para o termo proximal. Mapeado por nome para casar com os
        # parâmetros treináveis (named_parameters), ignorando buffers.
        use_fedprox = AGGREGATOR == "fedprox" and FEDPROX_MU > 0.0
        global_state = {}
        if use_fedprox:
            keys = list(self.model.state_dict().keys())
            global_state = {
                k: torch.tensor(v, device=self.device)
                for k, v in zip(keys, parameters)
            }

        total_loss = 0.0
        batch_count = 0
        correct_predictions = 0
        total_samples = 0
        start_time = time.time()

        agg_label = f"{AGGREGATOR}" + (f"(mu={FEDPROX_MU})" if use_fedprox else "")
        print(f"[BaselineClient {self.node_id}] Rodada {server_round}: "
              f"treinando ({agg_label})...")

        for _ in range(epochs):
            for images, labels in self.trainloader:
                images, labels = images.to(self.device), labels.to(self.device)
                images, labels = self._apply_attack(images, labels)
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)

                if use_fedprox:
                    prox = torch.zeros((), device=self.device)
                    for name, w in self.model.named_parameters():
                        w_g = global_state.get(name)
                        if w_g is not None:
                            prox = prox + ((w - w_g) ** 2).sum()
                    loss = loss + (FEDPROX_MU / 2.0) * prox

                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                batch_count += 1
                correct_predictions += (outputs.argmax(1) == labels).sum().item()
                total_samples += labels.size(0)

        train_time = time.time() - start_time
        avg_loss = total_loss / batch_count if batch_count else 0.0
        train_accuracy = correct_predictions / total_samples if total_samples else 0.0

        updated_params = [val.cpu().numpy() for _, val in self.model.state_dict().items()]

        metrics = {
            "avg_loss": float(avg_loss),
            "batches": int(batch_count),
            "loss": float(avg_loss),
            "accuracy": float(train_accuracy),
            "train_time": float(train_time),
            "train_samples": int(total_samples),
            "epochs": int(epochs),
            "node_id": int(self.node_id),
        }
        # Hook adicionado no Sprint 3 para refletir o estado de ataque do cliente
        # nas métricas, sem alterar a lógica de agregação.
        from .client import MALICIOUS, ATTACK_TYPE
        metrics["is_malicious"] = int(MALICIOUS)
        metrics["attack_type"] = ATTACK_TYPE if MALICIOUS else "none"
        metrics["aggregator"] = AGGREGATOR
        if use_fedprox:
            metrics["fedprox_mu"] = float(FEDPROX_MU)
        return updated_params, len(self.trainloader.dataset), metrics


def main_server():
    print("\n" + "=" * 70)
    print(" FLOWER FEDERATED LEARNING SERVER — BASELINE (sem blockchain/IPFS)")
    print("=" * 70)
    _rt = f"{_round_timeout:.0f}s" if _round_timeout else "∞"
    print(f" ROUNDS={ROUNDS}  MIN_CLIENTS={MIN_CLIENTS}  PORT={SERVER_ADDRESS}"
          f"  ROUND_TIMEOUT={_rt}")
    _agg = AGGREGATOR + (f" (mu={FEDPROX_MU})" if AGGREGATOR == "fedprox" else "")
    print(f" AGGREGATOR={_agg}")

    strategy = BaselineFLStrategy(min_clients=MIN_CLIENTS)
    config = fl.server.ServerConfig(num_rounds=ROUNDS, round_timeout=_round_timeout)

    experiment_start = time.time()
    try:
        fl.server.start_server(
            server_address=SERVER_ADDRESS,
            strategy=strategy,
            config=config,
            grpc_max_message_length=536870912,
        )
    except Exception as e:
        print(f"\n ERRO FATAL: {e}")
        strategy.metrics.save()
        sys.exit(1)

    total_elapsed = time.time() - experiment_start
    strategy.metrics.save()

    # ---- Resumo ----
    print("\n" + "=" * 70)
    print(" RESUMO BASELINE")
    print("=" * 70)
    for r in strategy.metrics.metrics["rounds"]:
        acc = r.get("accuracy")
        t = r.get("train_time_round_s")
        acc_str = f"{acc:.4f}" if acc is not None else "n/a"
        t_str = f"{t:.2f}s" if t is not None else "n/a"
        print(f"  Round {r['round']:>2}: accuracy={acc_str}  train_time={t_str}")
    print(f"\n Tempo total do experimento: {total_elapsed:.2f}s")
    print(f" Acurácia final: {strategy.metrics.metrics['final_accuracy']:.4f}")


def main_client():
    node_id = int(os.getenv("NODE_ID", "0"))
    num_nodes = int(os.getenv("NUM_NODES", str(MIN_CLIENTS)))

    print("\n" + "=" * 70)
    print(f" BASELINE CLIENT {node_id}/{num_nodes - 1} — conectando em {SERVER_ADDRESS}")
    print("=" * 70 + "\n")

    # pequeno delay para garantir que o servidor esteja pronto
    time.sleep(2)

    client = BaselineClient(node_id=node_id, num_nodes=num_nodes).to_client()
    fl.client.start_client(server_address=SERVER_ADDRESS, client=client)


if __name__ == "__main__":
    if os.getenv("BASELINE_AS_CLIENT") == "1":
        main_client()
    else:
        main_server()
