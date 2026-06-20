"""Experimento de segurança: clean vs frações de clientes maliciosos.

Para cada fração ``pct`` em ``--malicious-pct``, executa **uma run completa
de FL** com ``round(N * pct)`` clientes maliciosos (poisoning local via
``MALICIOUS=true`` em ``flower_fl/client.py``) e ``N - n_malicious`` clientes
honestos. Coleta:

- ``final_accuracy`` por fração
- ``n_flagged_total`` (soma de ``n_flagged`` por round, vinda do detector
  de anomalias do servidor — válido apenas no modo ``full``)
- ``accuracy_drop`` em relação à run com ``pct=0.0``

Modos:
  - ``baseline`` (default): usa ``flower_fl.baseline_runner`` em porta
    8081, sem blockchain/IPFS — ideal para CI sem Hardhat/Pinata.
  - ``full``: usa ``flower_fl.server`` + ``flower_fl.client`` (porta 8080),
    requer ``JOB_ADDRS`` no ``.env`` e contratos deployados.

Saída: ``{output_dir}/security_summary.json``.

Exemplo:
    python security_experiment.py --mode baseline --clients 4 --rounds 3 \\
        --malicious-pct 0.0,0.5 --attack-type label_flip
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


PYTHON = sys.executable or "python3"
LOGS_DIR = Path("logs/security")
VALID_ATTACKS = {"label_flip", "noise", "zero"}


def _mean_std(values: List[float]) -> Dict[str, float]:
    """Mean/std de uma lista (std amostral; 0.0 para <2 elementos)."""
    if not values:
        return {"mean": 0.0, "std": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "std": 0.0}
    return {
        "mean": float(statistics.fmean(values)),
        "std": float(statistics.stdev(values)),
    }


# ---------------------------------------------------------------------------
# Helpers (alinhados com multi_run.py)
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


# ---------------------------------------------------------------------------
# Run de uma única configuração (mode × pct)
# ---------------------------------------------------------------------------
def _make_client_env(
    base_env: Dict[str, str],
    node_id: int,
    is_malicious: bool,
    attack_type: str,
    attack_prob: float,
    baseline: bool,
) -> Dict[str, str]:
    env = base_env.copy()
    env["NODE_ID"] = str(node_id)
    env["MALICIOUS"] = "true" if is_malicious else "false"
    env["ATTACK_TYPE"] = attack_type
    env["ATTACK_PROB"] = str(attack_prob)
    if baseline:
        env["BASELINE_AS_CLIENT"] = "1"
    return env


def run_security_experiment(
    mode: str,
    num_clients: int,
    rounds: int,
    n_malicious: int,
    attack_type: str,
    attack_prob: float,
    metrics_file: Path,
    log_dir: Path,
    seed: int = 42,
) -> bool:
    """Spawn server + N clients (n_malicious dos quais maliciosos)."""
    base_env = os.environ.copy()
    base_env["ROUNDS"] = str(rounds)
    base_env["MIN_CLIENTS"] = str(num_clients)
    base_env["NUM_NODES"] = str(num_clients)
    base_env["DETECT_ANOMALIES"] = "true"
    base_env["SEED"] = str(seed)
    base_env["GRPC_POLL_STRATEGY"] = "poll"
    base_env["GRPC_ENABLE_FORK_SUPPORT"] = "1"
    # Evita oversubscrição de threads (N processos em poucos núcleos).
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
               "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        base_env.setdefault(_v, "1")

    if mode == "baseline":
        base_env["BASELINE_METRICS_FILE"] = str(metrics_file)
        base_env["BASELINE_SERVER_ADDRESS"] = "0.0.0.0:8081"
        server_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        client_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        baseline = True
    else:  # full
        base_env["METRICS_FILE"] = str(metrics_file)
        server_cmd = [PYTHON, "-m", "flower_fl.server"]
        client_cmd = [PYTHON, "-m", "flower_fl.client"]
        baseline = False

    server_log = log_dir / "server.log"
    server = _spawn(server_cmd, env=base_env, log_path=server_log)
    _wait_for_server(server, server_log, timeout=60.0)

    clients: List[subprocess.Popen] = []
    n_clean = num_clients - n_malicious
    try:
        for i in range(num_clients):
            is_mal = (i >= n_clean)
            env = _make_client_env(
                base_env, node_id=i,
                is_malicious=is_mal,
                attack_type=attack_type,
                attack_prob=attack_prob,
                baseline=baseline,
            )
            tag = "MAL" if is_mal else "OK "
            clients.append(_spawn(
                client_cmd,
                env=env,
                log_path=log_dir / f"client_{i}_{tag.strip()}.log",
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
def _extract_security_stats(metrics_file: Path) -> Dict[str, float]:
    with open(metrics_file) as f:
        data = json.load(f)

    final_acc = float(data.get("final_accuracy", 0.0))
    n_flagged_total = 0
    for r in data.get("rounds", []):
        if r.get("round", 0) == 0:
            continue
        flagged = r.get("n_flagged")
        if flagged is not None:
            n_flagged_total += int(flagged)
    return {
        "final_accuracy": final_acc,
        "n_flagged_total": n_flagged_total,
    }


def _print_table(rows: List[Dict[str, float]]) -> None:
    headers = ["pct_malicious", "n_malicious", "acc_mean±std",
               "drop_mean±std", "n_flagged_total"]
    widths = [max(len(h), 16) for h in headers]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = [
            f"{r['pct']:.2f}",
            str(r["n_malicious"]),
            f"{r['final_accuracy']:.4f}±{r.get('std_final_accuracy', 0.0):.4f}",
            f"{r['accuracy_drop']:.4f}±{r.get('std_accuracy_drop', 0.0):.4f}",
            str(r["n_flagged_total"]),
        ]
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--clients", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument(
        "--malicious-pct", type=str, default="0.0,0.2,0.4",
        help="Frações (0.0–1.0) de clientes maliciosos, separadas por vírgula.",
    )
    parser.add_argument(
        "--attack-type", choices=sorted(VALID_ATTACKS), default="label_flip",
    )
    parser.add_argument("--attack-prob", type=float, default=1.0)
    parser.add_argument("--mode", choices=["baseline", "full"], default="baseline")
    parser.add_argument(
        "--repetitions", type=int, default=1,
        help="Repetições por fração, com seeds distintas (mean ± std). "
             "Single 3-round runs são ruidosas; use >=3 para std confiável.",
    )
    parser.add_argument("--output-dir", type=str, default="results/security")
    args = parser.parse_args()

    if args.repetitions < 1:
        parser.error("--repetitions deve ser >= 1")

    try:
        pcts = [float(x.strip()) for x in args.malicious_pct.split(",") if x.strip()]
    except ValueError:
        parser.error("--malicious-pct deve conter apenas floats separados por vírgula")
    if not pcts:
        parser.error("--malicious-pct vazio")
    for p in pcts:
        if not (0.0 <= p <= 1.0):
            parser.error(f"fração fora de [0.0, 1.0]: {p}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat()
    _print_header(
        f" SECURITY EXP  mode={args.mode}  N={args.clients}  rounds={args.rounds}  "
        f"reps={args.repetitions}\n"
        f" attack={args.attack_type}  prob={args.attack_prob}  pcts={pcts}"
    )

    # raw[pct] = {"accs": [...], "flagged": [...], "n_malicious": int}
    # Listas indexadas por repetição (seed=rep) para permitir pareamento
    # clean-vs-malicious por seed ao calcular accuracy_drop.
    raw: Dict[float, Dict] = {}
    for pct in pcts:
        n_mal = round(args.clients * pct)
        accs: List[float] = []
        flagged: List[int] = []
        for rep in range(1, args.repetitions + 1):
            seed = rep
            sub = output_dir / f"pct{int(pct * 100)}" / f"rep{rep}"
            sub.mkdir(parents=True, exist_ok=True)
            log_sub = LOGS_DIR / f"pct{int(pct * 100)}" / f"rep{rep}"

            if args.mode == "baseline":
                target = sub / "baseline_metrics.json"
            else:
                target = sub / "server_metrics.json"

            _print_header(
                f" >> pct={pct:.2f}  n_malicious={n_mal}/{args.clients}  "
                f"rep={rep}/{args.repetitions}  seed={seed}"
            )
            ok = run_security_experiment(
                mode=args.mode,
                num_clients=args.clients,
                rounds=args.rounds,
                n_malicious=n_mal,
                attack_type=args.attack_type,
                attack_prob=args.attack_prob,
                metrics_file=target,
                log_dir=log_sub,
                seed=seed,
            )

            if not ok:
                print(f"   [WARN] métricas não encontradas em {target}")
                continue

            stats = _extract_security_stats(target)
            accs.append(float(stats["final_accuracy"]))
            flagged.append(int(stats["n_flagged_total"]))
            print(f"   final_accuracy={stats['final_accuracy']:.4f}  "
                  f"n_flagged_total={stats['n_flagged_total']}")

        raw[pct] = {"accs": accs, "flagged": flagged, "n_malicious": n_mal}

    # ---- Referência clean por repetição (pct=0.0 quando existir) ----
    ref_pct = 0.0 if 0.0 in raw and raw[0.0]["accs"] else min(raw.keys())
    ref_accs = raw[ref_pct]["accs"]

    results: Dict[str, Dict] = {}
    for pct in sorted(raw.keys()):
        accs = raw[pct]["accs"]
        flagged = raw[pct]["flagged"]
        # accuracy_drop pareado por seed quando há o mesmo nº de reps; senão
        # cai para diferença das médias.
        if accs and ref_accs and len(accs) == len(ref_accs):
            drops = [ra - a for ra, a in zip(ref_accs, accs)]
        else:
            ref_mean = _mean_std(ref_accs)["mean"] if ref_accs else 0.0
            drops = [ref_mean - a for a in accs]

        acc_stats = _mean_std(accs)
        drop_stats = _mean_std(drops)
        results[f"{pct}"] = {
            "final_accuracy": acc_stats["mean"],
            "std_final_accuracy": acc_stats["std"],
            "accuracy_drop": drop_stats["mean"],
            "std_accuracy_drop": drop_stats["std"],
            "n_flagged_total": int(sum(flagged)),
            "mean_n_flagged_per_run": _mean_std([float(x) for x in flagged])["mean"],
            "n_malicious": int(raw[pct]["n_malicious"]),
            "repetitions": len(accs),
        }

    summary = {
        "config": {
            "clients": args.clients,
            "rounds": args.rounds,
            "repetitions": args.repetitions,
            "attack_type": args.attack_type,
            "attack_prob": args.attack_prob,
            "mode": args.mode,
            "reference_pct": ref_pct,
            "started": started,
            "finished": datetime.now().isoformat(),
        },
        "results": results,
    }

    summary_path = output_dir / "security_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    _print_header(" SECURITY SUMMARY")
    print(f" salvo em: {summary_path}\n")
    rows = [
        {
            "pct": float(k),
            "n_malicious": v["n_malicious"],
            "final_accuracy": v["final_accuracy"],
            "std_final_accuracy": v.get("std_final_accuracy", 0.0),
            "accuracy_drop": v["accuracy_drop"],
            "std_accuracy_drop": v.get("std_accuracy_drop", 0.0),
            "n_flagged_total": v["n_flagged_total"],
        }
        for k, v in sorted(results.items(), key=lambda kv: float(kv[0]))
    ]
    _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
