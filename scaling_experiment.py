"""Experimento de escalabilidade × agregador para o CryptoFL.

Varia o número de clientes (até 10) e o agregador (FedAvg vs FedProx) usando o
modo *baseline* (Flower puro, sem blockchain/IPFS, rápido). Para cada
combinação (agregador × N clientes × repetição) sobe um servidor baseline na
porta 8081 e N clientes, coletando acurácia final e tempo de treino.

Saída:
- ``{output-dir}/scaling_summary.json``  — mean/std por (agregador, N).
- ``{output-dir}/scaling_accuracy.png``  — acurácia final vs nº de clientes.
- ``{output-dir}/scaling_time.png``      — tempo de treino vs nº de clientes.

Exemplo:
    KMP_DUPLICATE_LIB_OK=TRUE python scaling_experiment.py \\
        --clients-list 2,4,6,8,10 --rounds 3 --aggregators fedavg,fedprox \\
        --repetitions 1 --mu 0.1
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PYTHON = sys.executable or "python3"
LOGS_DIR = Path("logs/scaling")
BASELINE_PORT = 8081


# ---------------------------------------------------------------------------
# Helpers de processo / porta
# ---------------------------------------------------------------------------
def _print_header(text: str) -> None:
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def _spawn(cmd: List[str], env: Dict[str, str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w")
    return subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
        bufsize=1, universal_newlines=True,
    )


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def _wait_port_free(port: int, timeout: float = 20.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if _port_is_free(port):
            return
        time.sleep(0.5)


def _wait_for_server(proc: subprocess.Popen, log_path: Path, timeout: float = 60.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return
        if log_path.exists():
            try:
                content = log_path.read_text(errors="ignore")
            except OSError:
                content = ""
            if "Flower" in content or "FLOWER" in content or "gRPC server running" in content:
                return
        time.sleep(0.5)


def _terminate(proc: Optional[subprocess.Popen], timeout: float = 10.0) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()


def _mean_std(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "std": 0.0}
    return {"mean": float(statistics.fmean(values)),
            "std": float(statistics.stdev(values))}


# ---------------------------------------------------------------------------
# Execução de uma run (um agregador × N × repetição)
# ---------------------------------------------------------------------------
def run_one(aggregator: str, num_clients: int, rounds: int, mu: float,
            dataset: str, model: str, seed: int,
            metrics_file: Path, log_dir: Path,
            alpha: float = 0.5, min_fraction: float = 1.0) -> Optional[Dict[str, float]]:
    base_env = os.environ.copy()
    base_env["ROUNDS"] = str(rounds)
    # Fix 4: quorum relaxável. min_fraction=1.0 (default) mantém MIN_CLIENTS == N
    # — estatisticamente mais limpo para um estudo de escala (toda run usa N).
    # Valores <1.0 toleram a morte de clientes (ex.: 0.8 ⇒ aceita perder 20%),
    # de modo que um cliente morto não bloqueie o round.
    min_clients = max(2, int(num_clients * min_fraction))
    base_env["MIN_CLIENTS"] = str(min_clients)
    base_env["NUM_NODES"] = str(num_clients)   # ainda sobe N clientes
    base_env["SEED"] = str(seed)
    base_env["DATASET"] = dataset
    base_env["MODEL"] = model
    base_env["DIRICHLET_ALPHA"] = str(alpha)
    base_env["AGGREGATOR"] = aggregator
    base_env["FEDPROX_MU"] = str(mu)
    base_env["BASELINE_METRICS_FILE"] = str(metrics_file)
    base_env["BASELINE_SERVER_ADDRESS"] = f"0.0.0.0:{BASELINE_PORT}"
    base_env["GRPC_POLL_STRATEGY"] = "poll"
    base_env["GRPC_ENABLE_FORK_SUPPORT"] = "1"
    # Fix 1: round timeout finito para que um cliente morto não trave o sweep.
    # Rounds de MNIST são rápidos; CIFAR/ResNet precisam de um teto grande.
    default_timeout = 7200 if dataset.lower() == "cifar10" else 900
    base_env.setdefault("ROUND_TIMEOUT", str(default_timeout))
    # Evita o OMP Error #15 (libomp carregado em duplicidade) ao spawnar torch.
    base_env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
               "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        base_env.setdefault(_v, "1")

    _wait_port_free(BASELINE_PORT)

    server_log = log_dir / "server.log"
    server = _spawn([PYTHON, "-m", "flower_fl.baseline_runner"],
                    env=base_env, log_path=server_log)
    _wait_for_server(server, server_log, timeout=60.0)

    clients: List[subprocess.Popen] = []
    try:
        # Fix 3: delay entre spawns sensível ao dataset. 0.5s é curto demais
        # quando cada cliente precisa importar torch e carregar CIFAR — o
        # handshake gRPC corre e o servidor reporta "N-1 results and 1 failures".
        spawn_delay = 3.0 if dataset.lower() == "cifar10" else 1.0
        for i in range(num_clients):
            env = base_env.copy()
            env["NODE_ID"] = str(i)
            env["BASELINE_AS_CLIENT"] = "1"
            clients.append(_spawn([PYTHON, "-m", "flower_fl.baseline_runner"],
                                  env=env, log_path=log_dir / f"client_{i}.log"))
            time.sleep(spawn_delay)

        # Fix 3: confirma que todos os clientes seguem vivos antes de esperar o
        # servidor (detecta morte logo após o spawn).
        time.sleep(2)
        dead = [i for i, c in enumerate(clients) if c.poll() is not None]
        if dead:
            print(f"   [WARN] clients died right after spawn: {dead} "
                  f"(check {log_dir}/client_<i>.log)")

        # Fix 2: watchdog de wall-clock em torno de server.wait(). Teto rígido
        # por run (servidor + todos os clientes), proporcional a dataset/N.
        per_round = 1200 if dataset.lower() == "cifar10" else 120
        hard_ceiling = per_round * rounds * max(1, num_clients // 2) + 300
        deadline = time.time() + hard_ceiling
        while True:
            try:
                server.wait(timeout=10)
                break  # servidor terminou normalmente
            except subprocess.TimeoutExpired:
                if time.time() > deadline:
                    print(f"   [WATCHDOG] run exceeded {hard_ceiling}s — terminating")
                    break
                # se nenhum cliente está vivo e o servidor ainda espera, aborta.
                alive = sum(1 for c in clients if c.poll() is None)
                if alive == 0 and server.poll() is None:
                    print("   [WATCHDOG] all clients dead but server alive — aborting run")
                    break
    except KeyboardInterrupt:
        raise
    finally:
        for c in clients:
            _terminate(c)
        _terminate(server)

    if not metrics_file.exists():
        return None

    with open(metrics_file) as f:
        data = json.load(f)

    final_acc = float(data.get("final_accuracy", 0.0))
    total_time = 0.0
    for r in data.get("rounds", []):
        if r.get("round", 0) == 0:
            continue
        t = r.get("train_time_round_s")
        if t is None:
            cm = r.get("client_metrics") or []
            times = [c.get("train_time", 0.0) for c in cm]
            t = max(times) if times else 0.0
        total_time += float(t)

    return {"final_accuracy": final_acc, "train_time_s": total_time}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_results(summary: Dict, output_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mtick

    plt.style.use("seaborn-v0_8-darkgrid")
    plt.rcParams.update({"axes.titlesize": 13, "axes.labelsize": 11,
                         "legend.fontsize": 10, "figure.dpi": 120})

    results = summary["results"]
    aggregators = summary["config"]["aggregators"]
    cfg = summary["config"]
    ds = cfg.get("dataset", "mnist").upper()
    alpha = cfg.get("alpha")
    iid_tag = (f"non-IID α={alpha}" if str(cfg.get("dataset", "")).lower() == "cifar10"
               else "IID")
    subt = f"{ds} ({iid_tag}), {cfg.get('rounds')} rounds, {cfg.get('repetitions')} rep(s)"
    colors = {"fedavg": "#1f77b4", "fedprox": "#d62728"}
    markers = {"fedavg": "o", "fedprox": "s"}

    # ---- Figura 1: acurácia vs nº de clientes ----
    plt.figure(figsize=(8, 5))
    for agg in aggregators:
        ns, means, stds = [], [], []
        for n in sorted((int(k) for k in results), key=int):
            entry = results[str(n)].get(agg)
            if not entry:
                continue
            ns.append(n)
            means.append(entry["mean_accuracy"])
            stds.append(entry["std_accuracy"])
        if not ns:
            continue
        plt.errorbar(ns, means, yerr=stds, marker=markers.get(agg, "o"),
                     linewidth=2, capsize=4, label=agg.upper(),
                     color=colors.get(agg))
    plt.xlabel("Número de clientes")
    plt.ylabel("Acurácia final")
    plt.title(f"Acurácia final vs nº de clientes (FedAvg vs FedProx)\n{subt}")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.legend()
    plt.tight_layout()
    acc_path = output_dir / "scaling_accuracy.png"
    plt.savefig(acc_path, dpi=300)
    plt.close()
    print(f" figura salva: {acc_path}")

    # ---- Figura 2: tempo de treino vs nº de clientes ----
    plt.figure(figsize=(8, 5))
    for agg in aggregators:
        ns, means, stds = [], [], []
        for n in sorted((int(k) for k in results), key=int):
            entry = results[str(n)].get(agg)
            if not entry:
                continue
            ns.append(n)
            means.append(entry["mean_time_s"])
            stds.append(entry["std_time_s"])
        if not ns:
            continue
        plt.errorbar(ns, means, yerr=stds, marker=markers.get(agg, "o"),
                     linewidth=2, capsize=4, label=agg.upper(),
                     color=colors.get(agg))
    plt.xlabel("Número de clientes")
    plt.ylabel("Tempo de treino acumulado (s)")
    plt.title(f"Tempo de treino vs nº de clientes (FedAvg vs FedProx)\n{subt}")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.legend()
    plt.tight_layout()
    time_path = output_dir / "scaling_time.png"
    plt.savefig(time_path, dpi=300)
    plt.close()
    print(f" figura salva: {time_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clients-list", type=str, default="2,4,6,8,10")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--aggregators", type=str, default="fedavg,fedprox")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--mu", type=float, default=0.1,
                        help="Coeficiente proximal do FedProx.")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="Parâmetro Dirichlet (não-IID) para CIFAR-10.")
    parser.add_argument("--min-fraction", type=float, default=1.0,
                        help="Fração de clientes exigida por round (ex.: 0.8 tolera "
                             "perder 20%%). 1.0 (default) mantém MIN_CLIENTS == N, "
                             "estatisticamente mais limpo para o estudo de escala.")
    parser.add_argument("--dataset", type=str, default="mnist")
    parser.add_argument("--model", type=str, default="mnistnet")
    parser.add_argument("--output-dir", type=str, default="results/scaling")
    parser.add_argument("--plot-only", action="store_true",
                        help="Apenas re-plota a partir do scaling_summary.json existente.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "scaling_summary.json"

    if args.plot_only:
        with open(summary_path) as f:
            summary = json.load(f)
        plot_results(summary, output_dir)
        return 0

    clients_list = [int(x) for x in args.clients_list.split(",") if x.strip()]
    aggregators = [a.strip().lower() for a in args.aggregators.split(",") if a.strip()]
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat()
    _print_header(f" SCALING  aggregators={aggregators}  N={clients_list}  "
                  f"rounds={args.rounds}  reps={args.repetitions}  mu={args.mu}")

    # per_run[N][agg] = [ {final_accuracy, train_time_s}, ... ]
    per_run: Dict[int, Dict[str, List[Dict[str, float]]]] = {
        n: {a: [] for a in aggregators} for n in clients_list
    }

    for agg in aggregators:
        for n in clients_list:
            for rep in range(1, args.repetitions + 1):
                seed = rep
                tag = f"{agg}_n{n}_rep{rep}"
                _print_header(f" >> {agg.upper()}  N={n}  rep={rep}  seed={seed}")
                sub = output_dir / tag
                sub.mkdir(parents=True, exist_ok=True)
                metrics_file = sub / "baseline_metrics.json"
                log_dir = LOGS_DIR / tag

                t0 = time.time()
                stats = run_one(agg, n, args.rounds, args.mu, args.dataset,
                                args.model, seed, metrics_file, log_dir,
                                alpha=args.alpha, min_fraction=args.min_fraction)
                wall = time.time() - t0
                if stats is None:
                    print(f"   [WARN] {tag}: métricas não encontradas (ver {log_dir})")
                    continue
                per_run[n][agg].append(stats)
                print(f"   acc={stats['final_accuracy']:.4f}  "
                      f"train_time={stats['train_time_s']:.2f}s  wall={wall:.1f}s")

    # ---- Agregação ----
    results: Dict[str, Dict[str, Dict[str, float]]] = {}
    for n in clients_list:
        results[str(n)] = {}
        for agg in aggregators:
            runs = per_run[n][agg]
            if not runs:
                continue
            acc = _mean_std([r["final_accuracy"] for r in runs])
            tim = _mean_std([r["train_time_s"] for r in runs])
            results[str(n)][agg] = {
                "mean_accuracy": acc["mean"], "std_accuracy": acc["std"],
                "mean_time_s": tim["mean"], "std_time_s": tim["std"],
                "n_runs": len(runs),
            }

    summary = {
        "config": {
            "clients_list": clients_list,
            "aggregators": aggregators,
            "rounds": args.rounds,
            "repetitions": args.repetitions,
            "mu": args.mu,
            "alpha": args.alpha,
            "min_fraction": args.min_fraction,
            "dataset": args.dataset,
            "model": args.model,
            "started": started,
            "finished": datetime.now().isoformat(),
        },
        "results": results,
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    _print_header(" SUMMARY")
    print(f" salvo em: {summary_path}\n")
    header = f"{'agg':<9}{'N':>4}{'mean_acc':>11}{'std_acc':>10}{'mean_time_s':>13}{'std_time_s':>12}"
    print(header)
    print("-" * len(header))
    for n in clients_list:
        for agg in aggregators:
            e = results[str(n)].get(agg)
            if not e:
                continue
            print(f"{agg:<9}{n:>4}{e['mean_accuracy']:>11.4f}{e['std_accuracy']:>10.4f}"
                  f"{e['mean_time_s']:>13.2f}{e['std_time_s']:>12.2f}")

    plot_results(summary, output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
