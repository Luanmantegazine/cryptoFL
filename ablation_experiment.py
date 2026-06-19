"""Experimento de ablação: isola a contribuição de IPFS e da camada L2.

Para cada modo abaixo, executa **uma run completa de FL** com a mesma
configuração de clientes/rounds e coleta tempo médio por round, custo
total de gas e acurácia final:

- ``baseline``: Flower puro (sem blockchain, sem IPFS). Reusa
  ``flower_fl.baseline_runner``.
- ``no_ipfs``: blockchain ativa mas modelos passados diretamente via
  protocolo Flower (sem IPFS). Liga ``SKIP_IPFS=true`` em
  ``flower_fl.server`` / ``flower_fl.client``.
- ``full``: sistema completo atual (server.py + client.py com IPFS).

Modos ``baseline`` e ``no_ipfs`` **não** requerem Hardhat nem Pinata —
``no_ipfs`` mantém a estrutura on-chain via stub local (mesma semântica
do ``server.py``, mas sem chamadas IPFS) e, quando ``JOB_ADDRS`` não está
definido, as chamadas blockchain do server falham de forma graciosa
(o gás é 0 no metrics).

Saída: ``{output_dir}/ablation_summary.json``.

Exemplo:
    python ablation_experiment.py --clients 3 --rounds 3
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


PYTHON = sys.executable or "python3"
LOGS_DIR = Path("logs/ablation")
MODES = ("baseline", "no_ipfs", "full")


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


def _make_base_env(mode: str, rounds: int, num_clients: int, metrics_file: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["ROUNDS"] = str(rounds)
    env["MIN_CLIENTS"] = str(num_clients)
    env["NUM_NODES"] = str(num_clients)
    env["GRPC_POLL_STRATEGY"] = "poll"
    env["GRPC_ENABLE_FORK_SUPPORT"] = "1"

    if mode == "baseline":
        env["BASELINE_METRICS_FILE"] = str(metrics_file)
        env["BASELINE_SERVER_ADDRESS"] = "0.0.0.0:8081"
        env.pop("SKIP_IPFS", None)
    elif mode == "no_ipfs":
        env["METRICS_FILE"] = str(metrics_file)
        env["SKIP_IPFS"] = "true"
    else:  # full
        env["METRICS_FILE"] = str(metrics_file)
        env.pop("SKIP_IPFS", None)
    return env


def _run_mode(
    mode: str,
    num_clients: int,
    rounds: int,
    output_dir: Path,
) -> Path:
    """Executa uma run completa de FL para o modo dado e devolve o caminho do JSON."""
    mode_dir = output_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    log_dir = LOGS_DIR / mode

    if mode == "baseline":
        metrics_file = mode_dir / "server_metrics.json"
        # baseline_runner usa BASELINE_METRICS_FILE para nomear; espelhamos depois.
        baseline_target = mode_dir / "baseline_metrics.json"
        env = _make_base_env(mode, rounds, num_clients, baseline_target)
        server_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        client_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        client_extra = {"BASELINE_AS_CLIENT": "1"}
    else:
        metrics_file = mode_dir / "server_metrics.json"
        env = _make_base_env(mode, rounds, num_clients, metrics_file)
        server_cmd = [PYTHON, "-m", "flower_fl.server"]
        client_cmd = [PYTHON, "-m", "flower_fl.client"]
        client_extra = {}

    server_log = log_dir / "server.log"
    server = _spawn(server_cmd, env=env, log_path=server_log)
    _wait_for_server(server, server_log, timeout=60.0)

    clients: List[subprocess.Popen] = []
    try:
        for i in range(num_clients):
            c_env = env.copy()
            c_env["NODE_ID"] = str(i)
            c_env.update(client_extra)
            clients.append(_spawn(
                client_cmd, env=c_env,
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

    # baseline: espelha baseline_metrics.json → server_metrics.json para uniformizar
    if mode == "baseline" and baseline_target.exists() and not metrics_file.exists():
        try:
            metrics_file.write_text(baseline_target.read_text())
        except OSError as e:
            print(f"  [WARN] não consegui espelhar baseline metrics: {e}")

    return metrics_file


def _extract_stats(metrics_file: Path) -> Dict[str, float]:
    if not metrics_file.exists():
        print(f"  [WARN] {metrics_file} não encontrado — usando zeros")
        return {"mean_round_time_s": 0.0, "total_gas_eth": 0.0, "final_accuracy": 0.0}

    with open(metrics_file) as f:
        data = json.load(f)

    rounds = [r for r in data.get("rounds", []) if r.get("round", 0) > 0]
    times: List[float] = []
    for r in rounds:
        t = r.get("train_time_total_s")
        if t is None:
            cm = r.get("client_metrics") or []
            t = max((c.get("train_time", 0.0) for c in cm), default=0.0)
        times.append(float(t))

    mean_time = sum(times) / len(times) if times else 0.0
    total_gas = float(data.get("total_gas_eth", 0.0) or 0.0)
    final_acc = float(data.get("final_accuracy", 0.0) or 0.0)

    return {
        "mean_round_time_s": mean_time,
        "total_gas_eth": total_gas,
        "final_accuracy": final_acc,
    }


def _print_table(results: Dict[str, Dict[str, float]]) -> None:
    headers = ["mode", "mean_round_time_s", "total_gas_eth", "final_accuracy"]
    widths = [max(len(h), 18) for h in headers]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for mode in MODES:
        if mode not in results:
            continue
        s = results[mode]
        cells = [
            mode,
            f"{s['mean_round_time_s']:.2f}",
            f"{s['total_gas_eth']:.8f}",
            f"{s['final_accuracy']:.4f}",
        ]
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output-dir", type=str, default="results/ablation")
    parser.add_argument(
        "--modes", type=str, default=",".join(MODES),
        help="Modos a executar, separados por vírgula. Default: baseline,no_ipfs,full.",
    )
    args = parser.parse_args()

    requested = [m.strip() for m in args.modes.split(",") if m.strip()]
    for m in requested:
        if m not in MODES:
            parser.error(f"modo desconhecido: {m} (válidos: {MODES})")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat()
    _print_header(
        f" ABLATION  N={args.clients}  rounds={args.rounds}  modes={requested}"
    )

    results: Dict[str, Dict[str, float]] = {}
    for mode in requested:
        _print_header(f" >> mode={mode}")
        metrics_path = _run_mode(mode, args.clients, args.rounds, output_dir)
        results[mode] = _extract_stats(metrics_path)
        s = results[mode]
        print(f"   mean_round_time_s={s['mean_round_time_s']:.2f}  "
              f"total_gas_eth={s['total_gas_eth']:.8f}  "
              f"final_accuracy={s['final_accuracy']:.4f}")

    summary = {
        "config": {
            "clients": args.clients,
            "rounds": args.rounds,
            "modes": requested,
            "started": started,
            "finished": datetime.now().isoformat(),
        },
        "results": results,
    }

    summary_path = output_dir / "ablation_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    _print_header(" ABLATION SUMMARY")
    print(f" salvo em: {summary_path}\n")
    _print_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
