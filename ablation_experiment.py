"""Experimento de ablação: isola a contribuição de IPFS e da camada on-chain.

Três modos, executados como runs completas de FL com a mesma configuração de
clientes/rounds. Cada camada de descentralização é controlada por DUAS flags
independentes (``USE_IPFS`` e ``USE_ONCHAIN``):

- ``baseline`` (USE_IPFS=false, USE_ONCHAIN=false): Flower puro, sem blockchain
  e sem IPFS. Reusa ``flower_fl.baseline_runner``. Gás = 0.
- ``no_ipfs``  (USE_IPFS=false, USE_ONCHAIN=true): os pesos trafegam pelo
  protocolo Flower (sem IPFS), mas um **hash de conteúdo determinístico** é
  ancorado on-chain via a MESMA chamada do modo full (``publishGlobalModel``).
  Gás real, > 0 — isola o custo da camada on-chain sem o do IPFS.
- ``full``     (USE_IPFS=true, USE_ONCHAIN=true): sistema completo (IPFS +
  ancoragem on-chain).

Os modos ``no_ipfs`` e ``full`` REQUEREM Hardhat + ``JOB_ADDRS`` deployado; o
``full`` requer também IPFS acessível. Se algo faltar, o experimento PARA com
mensagem clara (nunca cai silenciosamente num modo que não gasta gás).

Repetições: cada modo roda ``--repetitions`` vezes com sementes distintas
(``--seeds``); agregamos média ± desvio de ``mean_round_time_s``,
``total_gas_eth`` e ``final_accuracy``. Os brutos ficam em
``{output_dir}/{mode}/rep{k}/`` e o consolidado em
``{output_dir}/ablation_summary.json``.

Exemplo:
    python ablation_experiment.py --modes baseline,no_ipfs,full \\
        --clients 3 --rounds 15 --repetitions 3 --output-dir results/ablation_full
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()  # garante JOB_ADDRS/JOB_ADDR/RPC_URL/IPFS_API_URL sem `source .env`

PYTHON = sys.executable or "python3"
LOGS_DIR = Path("logs/ablation")
MODES = ("baseline", "no_ipfs", "full")

# (USE_IPFS, USE_ONCHAIN) por modo — as duas camadas são independentes.
MODE_FLAGS: Dict[str, Tuple[bool, bool]] = {
    "baseline": (False, False),
    "no_ipfs": (False, True),
    "full": (True, True),
}


def _mean_std(values: List[float]) -> Tuple[float, float]:
    """Média e desvio-padrão amostral (std=0 se houver <2 valores)."""
    vals = [float(v) for v in values]
    if not vals:
        return 0.0, 0.0
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return mean, std


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


def _make_base_env(mode: str, rounds: int, num_clients: int,
                   metrics_file: Path, seed: int) -> Dict[str, str]:
    env = os.environ.copy()
    env["ROUNDS"] = str(rounds)
    env["MIN_CLIENTS"] = str(num_clients)
    env["NUM_NODES"] = str(num_clients)
    env["SEED"] = str(seed)
    env["GRPC_POLL_STRATEGY"] = "poll"
    env["GRPC_ENABLE_FORK_SUPPORT"] = "1"
    # Cada cliente/servidor roda em processo próprio; limitamos as threads de
    # BLAS/torch a 1 para evitar oversubscrição (N processos × T threads em
    # poucos núcleos trava o treino). Respeita override do ambiente externo.
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
               "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(_v, "1")

    use_ipfs, use_onchain = MODE_FLAGS[mode]
    # Camadas DESACOPLADAS: removemos a flag legada SKIP_IPFS para não haver
    # ambiguidade e setamos USE_IPFS / USE_ONCHAIN explicitamente por modo.
    env.pop("SKIP_IPFS", None)
    env["USE_IPFS"] = "true" if use_ipfs else "false"
    env["USE_ONCHAIN"] = "true" if use_onchain else "false"

    if mode == "baseline":
        env["BASELINE_METRICS_FILE"] = str(metrics_file)
        env["BASELINE_SERVER_ADDRESS"] = "0.0.0.0:8081"
    else:
        env["METRICS_FILE"] = str(metrics_file)
        # no_ipfs e full ancoram on-chain -> propaga JOB_ADDRS (servidor) e
        # JOB_ADDR (cliente) a partir do .env.
        if use_onchain:
            job_addrs = os.getenv("JOB_ADDRS", "").strip()
            env["JOB_ADDRS"] = job_addrs
            first = [a.strip() for a in job_addrs.split(",") if a.strip()]
            if first:
                env["JOB_ADDR"] = first[0]
    return env


def _run_mode(
    mode: str,
    num_clients: int,
    rounds: int,
    rep_dir: Path,
    seed: int,
    rep_label: str,
) -> Path:
    """Executa UMA repetição de FL para o modo dado e devolve o caminho do JSON."""
    rep_dir.mkdir(parents=True, exist_ok=True)
    log_dir = LOGS_DIR / mode / rep_label

    metrics_file = rep_dir / "server_metrics.json"
    baseline_target: Optional[Path] = None
    if mode == "baseline":
        # baseline_runner usa BASELINE_METRICS_FILE para nomear; espelhamos depois.
        baseline_target = rep_dir / "baseline_metrics.json"
        env = _make_base_env(mode, rounds, num_clients, baseline_target, seed)
        server_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        client_cmd = [PYTHON, "-m", "flower_fl.baseline_runner"]
        client_extra = {"BASELINE_AS_CLIENT": "1"}
    else:
        env = _make_base_env(mode, rounds, num_clients, metrics_file, seed)
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
    if mode == "baseline" and baseline_target is not None and baseline_target.exists():
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
        # Preferir train_time_round_s (= max train_time dos clientes); cair
        # para o campo legado train_time_total_s e, por fim, recalcular.
        t = r.get("train_time_round_s")
        if t is None:
            t = r.get("train_time_total_s")
        if t is None:
            cm = r.get("client_metrics") or []
            t = max((c.get("train_time", 0.0) for c in cm), default=0.0)
        times.append(float(t))

    mean_time = sum(times) / len(times) if times else 0.0
    total_gas = float(data.get("total_gas_eth", 0.0) or 0.0)
    final_acc = float(data.get("final_accuracy", 0.0) or 0.0)

    # Gás em regime permanente (steady-state): descartamos o PRIMEIRO round
    # ancorado on-chain — que carrega o custo único de SSTORE frio
    # (latestModelHash zero->nonzero) e a base fee mais alta — e reportamos a
    # média de gás por round dos demais. O bruto (total_gas_eth) é preservado.
    gas_series = [
        float(r.get("gas_eth") or 0.0)
        for r in sorted(data.get("rounds", []), key=lambda x: x.get("round", 0))
    ]
    anchored = [g for g in gas_series if g > 0.0]
    if len(anchored) > 1:
        steady_gas = sum(anchored[1:]) / len(anchored[1:])
    elif anchored:
        steady_gas = anchored[0]
    else:
        steady_gas = 0.0

    return {
        "mean_round_time_s": mean_time,
        "total_gas_eth": total_gas,
        "steady_gas_per_round_eth": steady_gas,
        "final_accuracy": final_acc,
    }


def _rpc_ok(rpc_url: str, timeout: float = 5.0) -> bool:
    """True se o endpoint JSON-RPC responde eth_chainId (Hardhat no ar)."""
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
    ).encode()
    req = urllib.request.Request(
        rpc_url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return "result" in body
    except Exception:
        return False


def _ipfs_ok(timeout: float = 5.0) -> bool:
    """True se há IPFS utilizável (Pinata via JWT ou daemon local acessível)."""
    if os.getenv("PINATA_JWT", "").strip():
        return True
    api = os.getenv("IPFS_API_URL", "").strip()
    if not api:
        return False
    url = f"{api.rstrip('/')}/api/v0/version"  # API do Kubo só aceita POST
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _preflight(modes: List[str]) -> List[str]:
    """Valida pré-condições dos modos. Devolve lista de problemas (vazia = ok).

    Nunca deixamos um modo rotulado no_ipfs/full rodar sem sua dependência —
    isso reintroduziria o bug de "no_ipfs sem gás == baseline".
    """
    problems: List[str] = []
    needs_onchain = [m for m in modes if MODE_FLAGS[m][1]]
    needs_ipfs = [m for m in modes if MODE_FLAGS[m][0]]

    if needs_onchain:
        job_addrs = os.getenv("JOB_ADDRS", "").strip()
        rpc = os.getenv("RPC_URL", "").strip()
        if not job_addrs:
            problems.append(
                f"modos {needs_onchain} precisam de JOB_ADDRS (JobContract deployado) no .env"
            )
        if not rpc:
            problems.append(f"modos {needs_onchain} precisam de RPC_URL no .env")
        elif not _rpc_ok(rpc):
            problems.append(
                f"modos {needs_onchain} precisam do Hardhat acessível em RPC_URL={rpc} "
                "(inicie o nó com `npx hardhat node`)"
            )

    if needs_ipfs and not _ipfs_ok():
        problems.append(
            f"modo(s) {needs_ipfs} precisam do IPFS (IPFS_API_URL acessível ou PINATA_JWT) "
            "— inicie o daemon com `ipfs daemon`"
        )
    return problems


def _print_table(results: Dict[str, Dict]) -> None:
    headers = ["mode", "time/round (s)", "total_gas (ETH)",
               "steady_gas/round (ETH)", "final_acc"]
    widths = [10, 20, 28, 28, 20]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for mode in MODES:
        if mode not in results:
            continue
        s = results[mode]
        cells = [
            mode,
            f"{s['mean_round_time_s']:.2f} ± {s.get('std_round_time_s', 0.0):.2f}",
            f"{s['total_gas_eth']:.8f} ± {s.get('std_total_gas_eth', 0.0):.2e}",
            f"{s.get('steady_gas_per_round_eth', 0.0):.8f} ± "
            f"{s.get('std_steady_gas_per_round_eth', 0.0):.2e}",
            f"{s['final_accuracy']:.4f} ± {s.get('std_final_accuracy', 0.0):.4f}",
        ]
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Repetições por modo, com sementes distintas. Default: 3.")
    parser.add_argument("--seeds", type=str, default="",
                        help="Sementes separadas por vírgula (ex.: 42,43,44). "
                             "Default: 42,43,... conforme --repetitions.")
    parser.add_argument("--output-dir", type=str, default="results/ablation_full")
    parser.add_argument(
        "--modes", type=str, default=",".join(MODES),
        help="Modos a executar, separados por vírgula. Default: baseline,no_ipfs,full.",
    )
    args = parser.parse_args()

    requested = [m.strip() for m in args.modes.split(",") if m.strip()]
    for m in requested:
        if m not in MODES:
            parser.error(f"modo desconhecido: {m} (válidos: {MODES})")

    if args.repetitions < 1:
        parser.error("--repetitions deve ser >= 1")

    # Resolve sementes (uma por repetição).
    if args.seeds.strip():
        try:
            seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        except ValueError:
            parser.error("--seeds deve ser uma lista de inteiros (ex.: 42,43,44)")
        if len(seeds) < args.repetitions:
            parser.error(
                f"--seeds tem {len(seeds)} valores mas --repetitions={args.repetitions}"
            )
        seeds = seeds[:args.repetitions]
    else:
        seeds = [42 + k for k in range(args.repetitions)]

    # Preflight: PARA se um modo que precisa de on-chain/IPFS não puder rodar.
    problems = _preflight(requested)
    if problems:
        _print_header(" ABLATION ABORTADA — pré-condições não atendidas")
        for p in problems:
            print(f"  ✗ {p}")
        print("\n  Nenhum modo foi executado (evitando resultados inválidos, "
              "p.ex. no_ipfs sem gás).")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now().isoformat()
    _print_header(
        f" ABLATION  N={args.clients}  rounds={args.rounds}  "
        f"reps={args.repetitions}  seeds={seeds}  modes={requested}"
    )

    results: Dict[str, Dict] = {}
    for mode in requested:
        use_ipfs, use_onchain = MODE_FLAGS[mode]
        _print_header(
            f" >> mode={mode}  (USE_IPFS={use_ipfs}, USE_ONCHAIN={use_onchain})"
        )
        per_rep: List[Dict] = []
        for k in range(args.repetitions):
            seed = seeds[k]
            rep_label = f"rep{k + 1}"
            rep_dir = output_dir / mode / rep_label
            print(f"   - {rep_label} (seed={seed}) ...")
            metrics_path = _run_mode(
                mode, args.clients, args.rounds, rep_dir, seed, rep_label
            )
            stats = _extract_stats(metrics_path)
            stats["seed"] = seed
            stats["rep"] = k + 1
            stats["metrics_file"] = str(metrics_path)
            per_rep.append(stats)
            print(f"     mean_round_time_s={stats['mean_round_time_s']:.2f}  "
                  f"total_gas_eth={stats['total_gas_eth']:.8f}  "
                  f"steady_gas/round={stats.get('steady_gas_per_round_eth', 0.0):.8f}  "
                  f"final_accuracy={stats['final_accuracy']:.4f}")

        t_mean, t_std = _mean_std([r["mean_round_time_s"] for r in per_rep])
        g_mean, g_std = _mean_std([r["total_gas_eth"] for r in per_rep])
        gs_mean, gs_std = _mean_std([r.get("steady_gas_per_round_eth", 0.0) for r in per_rep])
        a_mean, a_std = _mean_std([r["final_accuracy"] for r in per_rep])
        results[mode] = {
            # As médias mantêm os nomes legados (compat. com plot_ablation).
            "mean_round_time_s": t_mean, "std_round_time_s": t_std,
            "total_gas_eth": g_mean, "std_total_gas_eth": g_std,
            # Steady-state: gás médio por round on-chain, sem o round de warmup.
            "steady_gas_per_round_eth": gs_mean, "std_steady_gas_per_round_eth": gs_std,
            "final_accuracy": a_mean, "std_final_accuracy": a_std,
            "repetitions": args.repetitions,
            "seeds": seeds,
            "use_ipfs": use_ipfs,
            "use_onchain": use_onchain,
            "per_rep": per_rep,
        }

    summary = {
        "config": {
            "clients": args.clients,
            "rounds": args.rounds,
            "repetitions": args.repetitions,
            "seeds": seeds,
            "modes": requested,
            "started": started,
            "finished": datetime.now().isoformat(),
        },
        "results": results,
    }

    summary_path = output_dir / "ablation_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    _print_header(" ABLATION SUMMARY  (mean ± std)")
    print(f" salvo em: {summary_path}\n")
    _print_table(results)

    # BUG 1 — verificação explícita: no_ipfs deve ter gás real (> 0), distinto
    # do baseline (0), isolando o custo da camada on-chain.
    if "no_ipfs" in results:
        g = results["no_ipfs"]["total_gas_eth"]
        base_g = results.get("baseline", {}).get("total_gas_eth", 0.0)
        print()
        ok = g > 0.0
        print(f" [check] no_ipfs total_gas_eth = {g:.8f} ETH  -> "
              f"{'OK (> 0, camada on-chain ativa)' if ok else 'FALHA (== 0!)'}")
        print(f" [check] baseline total_gas_eth = {base_g:.8f} ETH (esperado 0)")
        if not ok:
            print(" [check] ⚠ no_ipfs sem gás: a ancoragem on-chain não ocorreu — "
                  "verifique Hardhat/JOB_ADDRS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
