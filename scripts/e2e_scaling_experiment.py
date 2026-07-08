"""Escalabilidade fim-a-fim (sistema completo) para o CryptoFL.

Roda o modo full (server + clients + IPFS + blockchain) para uma lista de N
clientes e mede:
- tempo total (wall-clock por experimento)
- throughput (updates/s e rounds/s)
- gas on-chain (somando receipts de tx_hash de server + clients)
- accuracy final

Saidas:
- results/e2e_scaling/e2e_scaling_summary.json
- results/e2e_scaling/e2e_scaling_summary.csv

Uso:
  python scripts/e2e_scaling_experiment.py \
      --clients-list 2,4,8,16,32 --rounds 3 --repetitions 1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multi_run import _extract_run_stats, run_full


load_dotenv()

DEFAULT_CLIENTS = [2, 4, 8, 16, 32]


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def _collect_tx_hashes(metrics: Dict) -> List[str]:
    hashes: List[str] = []
    for r in metrics.get("rounds", []):
        tx = r.get("tx_hash")
        if tx:
            hashes.append(str(tx))
        for c in (r.get("client_metrics") or []):
            ctx = c.get("tx_hash")
            if ctx:
                hashes.append(str(ctx))
    # de-dup preservando ordem
    uniq = []
    seen = set()
    for h in hashes:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return uniq


def _sum_gas_from_receipts(w3: Web3, tx_hashes: List[str]) -> Tuple[int, float, int]:
    gas_used_total = 0
    gas_eth_total = 0.0
    missing = 0
    for h in tx_hashes:
        try:
            rcpt = w3.eth.get_transaction_receipt(h)
            gas_used = int(rcpt["gasUsed"])
            eff = int(rcpt.get("effectiveGasPrice", 0) or 0)
            gas_used_total += gas_used
            gas_eth_total += (gas_used * eff) / 1e18
        except Exception:
            missing += 1
    return gas_used_total, gas_eth_total, missing


def _load_setup_gas_eth(path: Path) -> float:
    if not path.exists():
        return 0.0
    data = _load_json(path)
    ops = data.get("operations", [])
    setup_ops = {
        "registerRequester",
        "registerTrainer",
        "MakeOffer",
        "AcceptOffer",
        "signJobContract+fund",
        "signJobContract",
    }
    return float(sum(float(op.get("gas_eth", 0.0) or 0.0)
                     for op in ops if op.get("operation") in setup_ops))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Escalabilidade fim-a-fim (modo full)")
    p.add_argument("--clients-list", type=str, default=",".join(map(str, DEFAULT_CLIENTS)))
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--output-dir", type=Path, default=Path("results/e2e_scaling"))
    p.add_argument("--setup-breakdown", type=Path, default=Path("results/marketplace_gas_breakdown.json"))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    clients_list = [int(x.strip()) for x in args.clients_list.split(",") if x.strip()]

    rpc_url = os.getenv("RPC_URL", "").strip()
    if not rpc_url:
        raise RuntimeError("RPC_URL nao encontrado no ambiente/.env")
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        raise RuntimeError("Nao foi possivel conectar ao RPC. Hardhat esta no ar?")

    setup_gas_eth = _load_setup_gas_eth(args.setup_breakdown)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat()
    runs: Dict[str, Dict[str, List[float]]] = {
        str(n): {
            "total_time_s": [],
            "throughput_updates_s": [],
            "throughput_rounds_s": [],
            "accuracy": [],
            "gas_training_eth": [],
            "gas_training_used": [],
            "gas_with_setup_eth": [],
            "missing_receipts": [],
        }
        for n in clients_list
    }

    print("\n" + "=" * 82)
    print(f" E2E SCALING  N={clients_list} rounds={args.rounds} reps={args.repetitions}")
    print("=" * 82)

    for n in clients_list:
        for rep in range(1, args.repetitions + 1):
            seed = rep
            tag = f"n{n}_rep{rep}"
            exp_dir = raw_dir / tag
            exp_dir.mkdir(parents=True, exist_ok=True)
            metrics_file = exp_dir / "server_metrics.json"
            log_dir = Path("logs/e2e_scaling") / tag

            print(f"\n>> run {tag} ...")
            t0 = time.perf_counter()
            ok = run_full(n, args.rounds, seed, metrics_file, log_dir)
            t1 = time.perf_counter()
            wall = float(t1 - t0)

            if not ok or not metrics_file.exists():
                print(f"   [WARN] falhou: metrics nao encontrado ({metrics_file})")
                continue

            stats = _extract_run_stats(metrics_file)
            metrics = _load_json(metrics_file)
            train_rounds = [r for r in metrics.get("rounds", []) if int(r.get("round", 0)) > 0]
            if len(train_rounds) < args.rounds:
                print(
                    f"   [WARN] run incompleta: esperava {args.rounds} rounds de treino, "
                    f"mas encontrei {len(train_rounds)} ({metrics_file})"
                )
                continue
            tx_hashes = _collect_tx_hashes(metrics)
            gas_used, gas_eth, missing = _sum_gas_from_receipts(w3, tx_hashes)

            updates = n * args.rounds
            throughput_updates = float(updates / wall) if wall > 0 else 0.0
            throughput_rounds = float(args.rounds / wall) if wall > 0 else 0.0

            runs[str(n)]["total_time_s"].append(wall)
            runs[str(n)]["throughput_updates_s"].append(throughput_updates)
            runs[str(n)]["throughput_rounds_s"].append(throughput_rounds)
            runs[str(n)]["accuracy"].append(float(stats["final_accuracy"]))
            runs[str(n)]["gas_training_eth"].append(float(gas_eth))
            runs[str(n)]["gas_training_used"].append(float(gas_used))
            runs[str(n)]["gas_with_setup_eth"].append(float(setup_gas_eth + gas_eth))
            runs[str(n)]["missing_receipts"].append(float(missing))

            print(
                "   "
                f"wall={wall:.2f}s | "
                f"thr_updates={throughput_updates:.3f}/s | "
                f"gas_train={gas_eth:.8f} ETH | "
                f"acc={stats['final_accuracy']:.4f} | "
                f"missing_receipts={missing}"
            )

    rows = []
    for n in clients_list:
        k = str(n)
        if not runs[k]["total_time_s"]:
            continue
        rows.append(
            {
                "clients": n,
                "rounds": args.rounds,
                "repetitions": args.repetitions,
                "mean_total_time_s": _mean(runs[k]["total_time_s"]),
                "mean_throughput_updates_s": _mean(runs[k]["throughput_updates_s"]),
                "mean_throughput_rounds_s": _mean(runs[k]["throughput_rounds_s"]),
                "mean_accuracy": _mean(runs[k]["accuracy"]),
                "mean_gas_training_eth": _mean(runs[k]["gas_training_eth"]),
                "mean_gas_training_used": _mean(runs[k]["gas_training_used"]),
                "mean_gas_with_setup_eth": _mean(runs[k]["gas_with_setup_eth"]),
                "mean_missing_receipts": _mean(runs[k]["missing_receipts"]),
            }
        )

    summary = {
        "started_at": started,
        "ended_at": datetime.now().isoformat(),
        "config": {
            "clients_list": clients_list,
            "rounds": args.rounds,
            "repetitions": args.repetitions,
            "setup_breakdown": str(args.setup_breakdown),
            "setup_gas_eth": setup_gas_eth,
        },
        "results": rows,
    }

    json_out = args.output_dir / "e2e_scaling_summary.json"
    csv_out = args.output_dir / "e2e_scaling_summary.csv"
    json_out.write_text(json.dumps(summary, indent=2))

    with csv_out.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "clients",
                "rounds",
                "repetitions",
                "mean_total_time_s",
                "mean_throughput_updates_s",
                "mean_throughput_rounds_s",
                "mean_accuracy",
                "mean_gas_training_eth",
                "mean_gas_training_used",
                "mean_gas_with_setup_eth",
                "mean_missing_receipts",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print("\n" + "=" * 82)
    print(" RESUMO E2E SCALING")
    print("=" * 82)
    for r in rows:
        print(
            f"N={r['clients']:>2} | time={r['mean_total_time_s']:.2f}s | "
            f"thr={r['mean_throughput_updates_s']:.3f} upd/s | "
            f"gas={r['mean_gas_training_eth']:.8f} ETH | "
            f"acc={r['mean_accuracy']:.4f}"
        )

    print(f"\nJSON: {json_out}")
    print(f"CSV : {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
