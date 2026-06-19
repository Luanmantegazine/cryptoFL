"""Multi-run experiment driver para o CryptoFL.

Executa múltiplas configurações de clientes × repetições para coletar
estatísticas (mean ± std) de acurácia, gas e tempo de treino. Suporta
três modos:

- ``full``     : sistema completo (servidor + clientes com blockchain/IPFS).
                 Assume que os contratos já estão deployados e que
                 ``JOB_ADDRS``/``JOB_ADDR`` estão no ``.env``.
- ``baseline`` : roda apenas Flower puro via ``flower_fl.baseline_runner``.
- ``both``     : roda os dois modos em sequência por repetição.

Saída: ``{output_dir}/summary.json`` com mean/std por número de clientes,
além das métricas brutas copiadas para ``{output_dir}/n{N}_rep{R}/``.

Exemplo:
    python multi_run.py --clients-list 3,5 --rounds 3 --repetitions 3 --mode both
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from tabulate import tabulate  # type: ignore
    _HAS_TABULATE = True
except ImportError:  # pragma: no cover
    _HAS_TABULATE = False


PYTHON = sys.executable or "python3"
LOGS_DIR = Path("logs/multi_run")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _print_header(text: str) -> None:
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def _spawn(cmd: List[str], env: Dict[str, str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w")
    return subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        bufsize=1,
        universal_newlines=True,
    )


def _wait_for_server(proc: subprocess.Popen, log_path: Path, timeout: float = 30.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return
        if log_path.exists():
            try:
                content = log_path.read_text(errors="ignore")
            except OSError:
                content = ""
            if "Flower" in content or "Servidor" in content or "FLOWER" in content:
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
    return {
        "mean": float(statistics.fmean(values)),
        "std": float(statistics.stdev(values)),
    }


# ---------------------------------------------------------------------------
# Run a single experiment (one repetition × one N)
# ---------------------------------------------------------------------------
def run_full(num_clients: int, rounds: int, seed: int, metrics_file: Path,
             log_dir: Path) -> bool:
    """Roda o sistema completo (server + clients com blockchain).

    Requer que ``JOB_ADDRS`` (server) e ``JOB_ADDR`` (clients) estejam
    definidos no ambiente / `.env`.
    """
    base_env = os.environ.copy()
    base_env["ROUNDS"] = str(rounds)
    base_env["MIN_CLIENTS"] = str(num_clients)
    base_env["NUM_NODES"] = str(num_clients)
    base_env["SEED"] = str(seed)
    base_env["METRICS_FILE"] = str(metrics_file)
    base_env["GRPC_POLL_STRATEGY"] = "poll"
    base_env["GRPC_ENABLE_FORK_SUPPORT"] = "1"

    server_log = log_dir / "server.log"
    server = _spawn(
        [PYTHON, "-m", "flower_fl.server"],
        env=base_env,
        log_path=server_log,
    )
    _wait_for_server(server, server_log, timeout=60.0)

    clients: List[subprocess.Popen] = []
    try:
        for i in range(num_clients):
            env = base_env.copy()
            env["NODE_ID"] = str(i)
            clients.append(_spawn(
                [PYTHON, "-m", "flower_fl.client"],
                env=env,
                log_path=log_dir / f"client_{i}.log",
            ))
            time.sleep(1)

        server.wait()
    except KeyboardInterrupt:
        raise
    finally:
        for c in clients:
            _terminate(c)
        _terminate(server)

    return metrics_file.exists()


def run_baseline(num_clients: int, rounds: int, seed: int, metrics_file: Path,
                 log_dir: Path) -> bool:
    """Roda o baseline (Flower puro, sem blockchain/IPFS)."""
    base_env = os.environ.copy()
    base_env["ROUNDS"] = str(rounds)
    base_env["MIN_CLIENTS"] = str(num_clients)
    base_env["NUM_NODES"] = str(num_clients)
    base_env["SEED"] = str(seed)
    base_env["BASELINE_METRICS_FILE"] = str(metrics_file)
    base_env["BASELINE_SERVER_ADDRESS"] = "0.0.0.0:8081"
    base_env["GRPC_POLL_STRATEGY"] = "poll"
    base_env["GRPC_ENABLE_FORK_SUPPORT"] = "1"

    server_log = log_dir / "baseline_server.log"
    server = _spawn(
        [PYTHON, "-m", "flower_fl.baseline_runner"],
        env=base_env,
        log_path=server_log,
    )
    _wait_for_server(server, server_log, timeout=60.0)

    clients: List[subprocess.Popen] = []
    try:
        for i in range(num_clients):
            env = base_env.copy()
            env["NODE_ID"] = str(i)
            env["BASELINE_AS_CLIENT"] = "1"
            clients.append(_spawn(
                [PYTHON, "-m", "flower_fl.baseline_runner"],
                env=env,
                log_path=log_dir / f"baseline_client_{i}.log",
            ))
            time.sleep(1)

        server.wait()
    except KeyboardInterrupt:
        raise
    finally:
        for c in clients:
            _terminate(c)
        _terminate(server)

    return metrics_file.exists()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _extract_run_stats(metrics_file: Path) -> Dict[str, float]:
    """Extrai (final_accuracy, total_gas_eth, train_time_total_s) de um JSON."""
    with open(metrics_file) as f:
        data = json.load(f)

    final_acc = float(data.get("final_accuracy", 0.0))
    total_gas = float(data.get("total_gas_eth", 0.0))

    total_time = 0.0
    for r in data.get("rounds", []):
        if r.get("round", 0) == 0:
            continue  # round de inicialização, sem treino
        t = r.get("train_time_total_s")
        if t is None:
            cm = r.get("client_metrics") or []
            times = [c.get("train_time", 0.0) for c in cm]
            t = max(times) if times else 0.0
        total_time += float(t)

    return {
        "final_accuracy": final_acc,
        "total_gas_eth": total_gas,
        "train_time_s": total_time,
    }


def aggregate_summary(per_run: Dict[int, Dict[str, List[Dict[str, float]]]],
                      include_gas: bool) -> Dict:
    """Computa mean/std por número de clientes a partir das runs coletadas."""
    results: Dict[str, Dict[str, float]] = {}
    for n_clients, modes in per_run.items():
        # Para "both" temos resultados full+baseline; preferimos full para gas/acc.
        full_runs = modes.get("full", [])
        baseline_runs = modes.get("baseline", [])

        primary = full_runs if full_runs else baseline_runs
        accs = [r["final_accuracy"] for r in primary]
        times = [r["train_time_s"] for r in primary]
        entry: Dict[str, float] = {}

        acc_stats = _mean_std(accs)
        time_stats = _mean_std(times)
        entry["mean_accuracy"] = acc_stats["mean"]
        entry["std_accuracy"] = acc_stats["std"]
        entry["mean_time_s"] = time_stats["mean"]
        entry["std_time_s"] = time_stats["std"]

        if include_gas and full_runs:
            gas = [r["total_gas_eth"] for r in full_runs]
            gas_stats = _mean_std(gas)
            entry["mean_gas_eth"] = gas_stats["mean"]
            entry["std_gas_eth"] = gas_stats["std"]

        if baseline_runs:
            b_accs = [r["final_accuracy"] for r in baseline_runs]
            b_times = [r["train_time_s"] for r in baseline_runs]
            b_acc_stats = _mean_std(b_accs)
            b_time_stats = _mean_std(b_times)
            entry["baseline_mean_accuracy"] = b_acc_stats["mean"]
            entry["baseline_std_accuracy"] = b_acc_stats["std"]
            entry["baseline_mean_time_s"] = b_time_stats["mean"]
            entry["baseline_std_time_s"] = b_time_stats["std"]

        results[str(n_clients)] = entry

    return results


def print_summary_table(summary: Dict) -> None:
    headers = ["N", "mean_acc", "std_acc", "mean_time_s", "std_time_s",
               "mean_gas_eth", "std_gas_eth"]
    rows = []
    for n, vals in sorted(summary["results"].items(), key=lambda kv: int(kv[0])):
        rows.append([
            n,
            f"{vals.get('mean_accuracy', 0):.4f}",
            f"{vals.get('std_accuracy', 0):.4f}",
            f"{vals.get('mean_time_s', 0):.2f}",
            f"{vals.get('std_time_s', 0):.2f}",
            f"{vals.get('mean_gas_eth', 0):.8f}" if "mean_gas_eth" in vals else "-",
            f"{vals.get('std_gas_eth', 0):.8f}" if "std_gas_eth" in vals else "-",
        ])

    print()
    if _HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="github"))
    else:
        widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
        line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        print(line)
        print("-" * len(line))
        for r in rows:
            print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clients-list", type=str, default="5,10,15,20,25",
                        help="Lista de N clientes, separados por vírgula.")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Repetições por configuração (mínimo 3 recomendado).")
    parser.add_argument("--mode", choices=["full", "baseline", "both"], default="both")
    parser.add_argument("--output-dir", type=str, default="results/multi_run")
    args = parser.parse_args()

    if args.repetitions < 1:
        parser.error("--repetitions deve ser >= 1")
    if args.repetitions < 3:
        print(f"AVISO: --repetitions={args.repetitions} < 3 (recomendado para std confiável).")

    try:
        clients_list = [int(x.strip()) for x in args.clients_list.split(",") if x.strip()]
    except ValueError:
        parser.error("--clients-list deve ser uma lista de inteiros separados por vírgula")
    if not clients_list:
        parser.error("--clients-list não pode estar vazia")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    modes_to_run: List[str]
    if args.mode == "both":
        modes_to_run = ["full", "baseline"]
    else:
        modes_to_run = [args.mode]

    per_run: Dict[int, Dict[str, List[Dict[str, float]]]] = {
        n: {"full": [], "baseline": []} for n in clients_list
    }

    started = datetime.now().isoformat()
    _print_header(f" MULTI-RUN  modes={modes_to_run}  N={clients_list}  "
                  f"rounds={args.rounds}  reps={args.repetitions}")

    # Set seeds inside this driver too (for reproducibility of any local code).
    try:
        import torch
        import numpy as np
    except ImportError:
        torch = None
        np = None

    for n_clients in clients_list:
        for rep in range(1, args.repetitions + 1):
            seed = rep
            if torch is not None:
                torch.manual_seed(seed)
            if np is not None:
                np.random.seed(seed)

            sub = output_dir / f"n{n_clients}_rep{rep}"
            sub.mkdir(parents=True, exist_ok=True)
            log_sub = LOGS_DIR / f"n{n_clients}_rep{rep}"

            for mode in modes_to_run:
                _print_header(f" >> N={n_clients} rep={rep} mode={mode} seed={seed}")
                if mode == "full":
                    target = sub / "server_metrics.json"
                    ok = run_full(n_clients, args.rounds, seed, target, log_sub)
                else:
                    target = sub / "baseline_metrics.json"
                    ok = run_baseline(n_clients, args.rounds, seed, target, log_sub)

                if not ok:
                    print(f"   [WARN] run {mode} N={n_clients} rep={rep}: "
                          f"métricas não encontradas em {target}")
                    continue

                stats = _extract_run_stats(target)
                per_run[n_clients][mode].append(stats)
                print(f"   acc={stats['final_accuracy']:.4f}  "
                      f"gas={stats['total_gas_eth']:.6f}  "
                      f"time={stats['train_time_s']:.2f}s")

    include_gas = "full" in modes_to_run
    summary = {
        "config": {
            "clients_list": clients_list,
            "rounds": args.rounds,
            "repetitions": args.repetitions,
            "modes": modes_to_run,
            "started": started,
            "finished": datetime.now().isoformat(),
        },
        "results": aggregate_summary(per_run, include_gas=include_gas),
    }

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    _print_header(" SUMMARY")
    print(f" salvo em: {summary_path}")
    print_summary_table(summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
