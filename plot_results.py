import json
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from pathlib import Path

plt.style.use("seaborn-v0_8-darkgrid")
plt.rcParams.update({
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "legend.fontsize": 10,
    "figure.dpi": 120,
})

# ── Estilo global ────────────────────────────────────────────────────
PLOT_DPI = 300
PLOT_FIGSIZE = (8, 5)
PLOT_PALETTE = {
    "full":      "#1f77b4",   # azul — sistema completo
    "baseline":  "#ff7f0e",   # laranja — baseline sem blockchain
    "flagged":   "#d62728",   # vermelho — updates suspeitos
    "clean":     "#2ca02c",   # verde — runs limpas
    "malicious": "#9467bd",   # roxo — runs com ataque
    "gas":       "#8c564b",   # marrom — custos de gas
}


def _save(fig, path: str):
    """Salva figura com DPI e bbox padrões e fecha."""
    fig.savefig(path, dpi=PLOT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {path}")


def plot_metrics_publishable(metrics_file="results/server_metrics.json"):
    # 1. Load data
    path = Path(metrics_file)
    if not path.exists():
        path = Path("server_metrics.json")
        if not path.exists():
            print(f"Error: File '{metrics_file}' not found.")
            return

    with open(path) as f:
        data = json.load(f)

    # 2. Extract rounds (ignore round 0)
    all_rounds = data.get("rounds", [])
    train_rounds = [r for r in all_rounds if r["round"] > 0]

    if not train_rounds:
        print("Warning: No training rounds found.")
        return

    rounds = [r["round"] for r in train_rounds]
    gas_fees = [r.get("gas_eth") or 0.0 for r in train_rounds]
    num_clients = [r.get("num_clients") or 1 for r in train_rounds]
    gas_per_client = [g / n for g, n in zip(gas_fees, num_clients)]

    # ---------------------------------------
    # Extract MACHINE LEARNING metrics
    # ---------------------------------------
    round_avg_loss = []
    round_avg_train_time = []
    round_total_examples = []
    round_total_batches = []
    round_accuracy = []
    round_loss = []
    client_accuracy_by_round = {}

    for r in train_rounds:
        cm = r.get("client_metrics", [])

        losses = [c.get("avg_loss", 0) for c in cm]
        times = [c.get("train_time", 0) for c in cm]
        examples = [c.get("num_examples", 0) for c in cm]
        batches = [c.get("batches", 0) for c in cm]

        aggregated = r.get("aggregated_metrics", {}) or {}

        # aggregated
        round_avg_loss.append(sum(losses) / len(losses))
        round_avg_train_time.append(sum(times) / len(times))
        round_total_examples.append(sum(examples))
        round_total_batches.append(sum(batches))

        for metric in cm:
            node_id = metric.get("node_id", metric.get("client_id", "?"))
            accuracy = metric.get("accuracy")
            if accuracy is None:
                continue
            client_accuracy_by_round.setdefault(node_id, {"rounds": [], "accuracy": []})
            client_accuracy_by_round[node_id]["rounds"].append(r["round"])
            client_accuracy_by_round[node_id]["accuracy"].append(accuracy)

        round_accuracy.append(aggregated.get("accuracy", r.get("accuracy", 0)))
        round_loss.append(aggregated.get("loss", aggregated.get("avg_loss", 0)))

    # ------------------------------
    # PLOT 1 – Gas Per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, gas_fees, marker="o", linewidth=2, color=PLOT_PALETTE["full"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Gas (ETH)")
    ax.set_title("Gas Cost per Round")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_gas_per_round.png")

    # ------------------------------
    # PLOT 2 – Cumulative Gas
    # ------------------------------
    cumulative = [sum(gas_fees[: i + 1]) for i in range(len(gas_fees))]
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, cumulative, marker="s", linewidth=2, color=PLOT_PALETTE["baseline"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Cumulative Gas (ETH)")
    ax.set_title("Cumulative Gas Consumption")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_cumulative_gas.png")

    # ------------------------------
    # PLOT 3 – Gas Per Client
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, gas_per_client, marker="^", linewidth=2, color=PLOT_PALETTE["clean"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Gas per Client (ETH)")
    ax.set_title("Gas Cost Per Client")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_gas_per_client.png")

    # ------------------------------
    # PLOT 4 – Avg Loss per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, round_avg_loss, marker="o", linewidth=2, color=PLOT_PALETTE["flagged"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Average Loss")
    ax.set_title("Average Client Loss per Round")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_avg_loss_round.png")

    # ------------------------------
    # PLOT 5 – Avg Training Time per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, round_avg_train_time, marker="o", linewidth=2, color=PLOT_PALETTE["malicious"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Average Training Time (s)")
    ax.set_title("Training Time per Round")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_train_time_round.png")

    # ------------------------------
    # PLOT 6 – Total Examples per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, round_avg_loss, marker="o", linewidth=2, color=PLOT_PALETTE["flagged"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Total Training Examples")
    ax.set_title("Total Examples Processed per Round")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_total_examples_round.png")

    # ------------------------------
    # PLOT 7 – Global Accuracy per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, round_accuracy, marker="o", linewidth=2, color="#e377c2")
    ax.set_xlabel("Round")
    ax.set_ylabel("Accuracy")
    ax.set_title("Global Accuracy per Round")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_accuracy_round.png")

    # ------------------------------
    # PLOT 8 – Global Loss per Round
    # ------------------------------
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, round_loss, marker="o", linewidth=2, color="#7f7f7f")
    ax.set_xlabel("Round")
    ax.set_ylabel("Loss")
    ax.set_title("Global Loss per Round")
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    _save(fig, "plot_loss_round.png")

    # ------------------------------
    # PLOT 9 – Client Accuracy per Round
    # ------------------------------
    if client_accuracy_by_round:
        fig, ax = plt.subplots(figsize=(9, 6))
        for node_id, values in sorted(client_accuracy_by_round.items()):
            ax.plot(
                values["rounds"],
                values["accuracy"],
                marker="o",
                linewidth=2,
                label=f"Client {node_id}",
            )
        ax.set_xlabel("Round")
        ax.set_ylabel("Accuracy")
        ax.set_title("Client Accuracy per Round")
        ax.legend()
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
        _save(fig, "plot_client_accuracy_round.png")


def _round_total_time(round_data):
    """Tempo total do round (preferindo `train_time_total_s`)."""
    t = round_data.get("train_time_total_s")
    if t is not None:
        return float(t)
    cm = round_data.get("client_metrics") or []
    if not cm:
        return 0.0
    # Tempo do round ~ max(train_time) (clientes em paralelo).
    return float(max(c.get("train_time", 0.0) for c in cm))


def plot_baseline_comparison(full_metrics_file, baseline_metrics_file, output_prefix=""):
    """Compara sistema completo vs baseline (acurácia por round + tempo por round)."""
    full_path = Path(full_metrics_file)
    base_path = Path(baseline_metrics_file)
    if not full_path.exists() or not base_path.exists():
        print(f"plot_baseline_comparison: arquivo(s) não encontrado(s)")
        return

    with open(full_path) as f:
        full = json.load(f)
    with open(base_path) as f:
        base = json.load(f)

    full_rounds = [r for r in full.get("rounds", []) if r.get("round", 0) > 0]
    base_rounds = [r for r in base.get("rounds", []) if r.get("round", 0) > 0]

    if not full_rounds or not base_rounds:
        print("plot_baseline_comparison: sem rounds para comparar")
        return

    f_x = [r["round"] for r in full_rounds]
    f_acc = [r.get("accuracy") or (r.get("aggregated_metrics") or {}).get("accuracy", 0)
             for r in full_rounds]
    b_x = [r["round"] for r in base_rounds]
    b_acc = [r.get("accuracy") or (r.get("aggregated_metrics") or {}).get("accuracy", 0)
             for r in base_rounds]

    # ---- Acurácia ----
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(f_x, f_acc, marker="o", linewidth=2, label="Sistema completo (blockchain)",
            color=PLOT_PALETTE["full"])
    ax.plot(b_x, b_acc, marker="s", linewidth=2, label="Baseline (Flower puro)",
            color=PLOT_PALETTE["baseline"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy per Round: Full vs Baseline")
    ax.legend()
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    out_acc = f"{output_prefix}plot_baseline_vs_full_accuracy.png"
    _save(fig, out_acc)

    # ---- Tempo (barras agrupadas por round) ----
    rounds_union = sorted(set(f_x) | set(b_x))
    f_time_map = {r["round"]: _round_total_time(r) for r in full_rounds}
    b_time_map = {r["round"]: _round_total_time(r) for r in base_rounds}
    f_times = [f_time_map.get(r, 0.0) for r in rounds_union]
    b_times = [b_time_map.get(r, 0.0) for r in rounds_union]

    import numpy as _np
    width = 0.4
    x_idx = _np.arange(len(rounds_union))
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.bar(x_idx - width / 2, f_times, width=width, label="Sistema completo",
           color=PLOT_PALETTE["full"])
    ax.bar(x_idx + width / 2, b_times, width=width, label="Baseline",
           color=PLOT_PALETTE["baseline"])
    ax.set_xticks(x_idx)
    ax.set_xticklabels(rounds_union)
    ax.set_xlabel("Round")
    ax.set_ylabel("Total Training Time (s)")
    ax.set_title("Overhead de Tempo por Round: Full vs Baseline")
    ax.legend()
    out_time = f"{output_prefix}plot_overhead_time.png"
    _save(fig, out_time)

    print(f"Generated: {out_acc}, {out_time}")


def plot_multi_run_summary(summary_json_file, output_prefix=""):
    """Plot mean±std de acurácia e gas em função do número de clientes."""
    path = Path(summary_json_file)
    if not path.exists():
        print(f"plot_multi_run_summary: {summary_json_file} não encontrado")
        return

    with open(path) as f:
        summary = json.load(f)

    results = summary.get("results", {})
    if not results:
        print("plot_multi_run_summary: 'results' vazio")
        return

    ns = sorted(int(k) for k in results.keys())
    accs = [results[str(n)].get("mean_accuracy", 0.0) for n in ns]
    accs_std = [results[str(n)].get("std_accuracy", 0.0) for n in ns]

    # ---- Acurácia mean ± std ----
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(ns, accs, marker="o", linewidth=2, color=PLOT_PALETTE["full"], label="Mean accuracy")
    lower = [a - s for a, s in zip(accs, accs_std)]
    upper = [a + s for a, s in zip(accs, accs_std)]
    ax.fill_between(ns, lower, upper, alpha=0.25, color=PLOT_PALETTE["full"],
                    label="± 1 std")
    ax.set_xlabel("Number of Clients (N)")
    ax.set_ylabel("Final Accuracy")
    ax.set_title("Accuracy vs N Clients (mean ± std)")
    ax.legend()
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    out_acc = f"{output_prefix}plot_accuracy_mean_std.png"
    _save(fig, out_acc)
    print(f"Generated: {out_acc}")

    # ---- Gas mean ± std (se disponível) ----
    has_gas = any("mean_gas_eth" in results[str(n)] for n in ns)
    if not has_gas:
        return

    gas = [results[str(n)].get("mean_gas_eth", 0.0) for n in ns]
    gas_std = [results[str(n)].get("std_gas_eth", 0.0) for n in ns]
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(ns, gas, marker="o", linewidth=2, color=PLOT_PALETTE["flagged"], label="Mean gas (ETH)")
    g_lower = [g - s for g, s in zip(gas, gas_std)]
    g_upper = [g + s for g, s in zip(gas, gas_std)]
    ax.fill_between(ns, g_lower, g_upper, alpha=0.25, color=PLOT_PALETTE["flagged"],
                    label="± 1 std")
    ax.set_xlabel("Number of Clients (N)")
    ax.set_ylabel("Total Gas (ETH)")
    ax.set_title("Gas vs N Clients (mean ± std)")
    ax.legend()
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    out_gas = f"{output_prefix}plot_gas_mean_std.png"
    _save(fig, out_gas)
    print(f"Generated: {out_gas}")


def plot_gas_breakdown(breakdown_file, output_prefix=""):
    """Plot empilhado por operação × round (escala 1e-5 ETH)."""
    path = Path(breakdown_file)
    if not path.exists():
        print(f"plot_gas_breakdown: {breakdown_file} não encontrado")
        return

    with open(path) as f:
        entries = json.load(f)

    if not entries:
        print("plot_gas_breakdown: arquivo vazio")
        return

    rounds = sorted({e["round"] for e in entries})
    operations = sorted({e["operation"] for e in entries})

    # gas[op][round_idx] = soma de gas_eth daquela op naquele round
    gas = {op: [0.0] * len(rounds) for op in operations}
    round_idx = {r: i for i, r in enumerate(rounds)}
    for e in entries:
        gas[e["operation"]][round_idx[e["round"]]] += float(e.get("gas_eth", 0.0))

    import numpy as _np
    x = _np.arange(len(rounds))
    bottom = _np.zeros(len(rounds))

    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    colors = plt.get_cmap("tab10").colors
    for i, op in enumerate(operations):
        values = _np.array(gas[op]) / 1e-5  # exibir em unidades de 1e-5 ETH
        ax.bar(x, values, bottom=bottom, label=op, color=colors[i % len(colors)])
        bottom += values

    ax.set_xticks(x)
    ax.set_xticklabels(rounds)
    ax.set_xlabel("Round")
    ax.set_ylabel("Gas (×1e-5 ETH)")
    ax.set_title("Gas Breakdown por Operação e Round")
    ax.legend()
    out_path = f"{output_prefix}plot_gas_breakdown.png"
    _save(fig, out_path)
    print(f"Generated: {out_path}")


def plot_update_norms(metrics_file, output_prefix=""):
    """Plot mean ± std da norma L2 dos updates por round, marcando flagged."""
    path = Path(metrics_file)
    if not path.exists():
        print(f"plot_update_norms: {metrics_file} não encontrado")
        return

    with open(path) as f:
        data = json.load(f)

    rounds = []
    means = []
    stds = []
    flagged = []
    for r in data.get("rounds", []):
        if r.get("round", 0) == 0:
            continue
        m = r.get("mean_update_norm")
        s = r.get("std_update_norm")
        if m is None:
            continue
        rounds.append(r["round"])
        means.append(float(m))
        stds.append(float(s) if s is not None else 0.0)
        flagged.append(int(r.get("n_flagged") or 0))

    if not rounds:
        print("plot_update_norms: sem dados de norma para plotar")
        return

    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(rounds, means, marker="o", linewidth=2, color=PLOT_PALETTE["full"],
            label="mean update norm")
    lower = [m - s for m, s in zip(means, stds)]
    upper = [m + s for m, s in zip(means, stds)]
    ax.fill_between(rounds, lower, upper, alpha=0.25, color=PLOT_PALETTE["full"],
                    label="± 1 std")

    # Anota n_flagged > 0 acima do ponto
    for x, y, n in zip(rounds, means, flagged):
        if n > 0:
            ax.annotate(f"⚠ {n}", xy=(x, y), xytext=(0, 10),
                        textcoords="offset points", ha="center",
                        color=PLOT_PALETTE["flagged"], fontsize=9)

    ax.set_xlabel("Round")
    ax.set_ylabel("Update L2 norm")
    ax.set_title("Update Norms per Round (mean ± std)")
    ax.legend()
    ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    out_path = f"{output_prefix}plot_update_norms.png"
    _save(fig, out_path)
    print(f"Generated: {out_path}")


def plot_security_summary(summary_file, output_prefix=""):
    """Plots de segurança a partir de `security_summary.json`.

    Gera:
      - plot_security_accuracy_drop.png: linha de final_accuracy +
        barras de accuracy_drop por fração de clientes maliciosos.
      - plot_security_flagged.png: linha de n_flagged_total por fração.
    """
    path = Path(summary_file)
    if not path.exists():
        print(f"plot_security_summary: {summary_file} não encontrado")
        return

    with open(path) as f:
        summary = json.load(f)

    results = summary.get("results", {})
    if not results:
        print("plot_security_summary: 'results' vazio")
        return

    # Mapeia cada chave string para seu valor float, mantendo ordem crescente.
    pairs = sorted(((float(k), v) for k, v in results.items()), key=lambda kv: kv[0])
    pcts = [p for p, _ in pairs]
    final_accs = [float(v.get("final_accuracy", 0.0)) for _, v in pairs]
    drops = [float(v.get("accuracy_drop", 0.0)) for _, v in pairs]
    flagged = [int(v.get("n_flagged_total", 0)) for _, v in pairs]

    # ---- Accuracy + drop ----
    fig, ax1 = plt.subplots(figsize=PLOT_FIGSIZE)
    ax1.plot(pcts, final_accs, marker="o", linewidth=2, color=PLOT_PALETTE["full"],
             label="Final accuracy")
    ax1.set_xlabel("Malicious clients fraction")
    ax1.set_ylabel("Final accuracy", color=PLOT_PALETTE["full"])
    ax1.tick_params(axis="y", labelcolor=PLOT_PALETTE["full"])
    ax1.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))

    ax2 = ax1.twinx()
    width = (max(pcts) - min(pcts)) / max(len(pcts), 2) * 0.4 if len(pcts) > 1 else 0.05
    ax2.bar(pcts, drops, width=width, alpha=0.5, color=PLOT_PALETTE["flagged"],
            label="Accuracy drop")
    ax2.set_ylabel("Accuracy drop", color=PLOT_PALETTE["flagged"])
    ax2.tick_params(axis="y", labelcolor=PLOT_PALETTE["flagged"])

    ax1.set_title("Security: accuracy vs. malicious fraction")
    out_acc = f"{output_prefix}plot_security_accuracy_drop.png"
    _save(fig, out_acc)
    print(f"Generated: {out_acc}")

    # ---- Flagged ----
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.plot(pcts, flagged, marker="s", linewidth=2, color=PLOT_PALETTE["malicious"])
    ax.set_xlabel("Malicious clients fraction")
    ax.set_ylabel("Total flagged updates")
    ax.set_title("Security: anomaly detector flags vs. malicious fraction")
    out_flag = f"{output_prefix}plot_security_flagged.png"
    _save(fig, out_flag)
    print(f"Generated: {out_flag}")


def plot_client_accuracy_individual(metrics_dir: str, output_dir: str):
    """Para cada `server_metrics.json` em ``metrics_dir`` (recursivo), gera
    um PNG individual com a curva de acurácia por round para cada cliente,
    salvo em ``output_dir/accuracy_n{N}_clients.png``."""
    base = Path(metrics_dir)
    if not base.exists():
        print(f"plot_client_accuracy_individual: {metrics_dir} não encontrado")
        return

    out_base = Path(output_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    files = list(base.rglob("server_metrics.json"))
    if not files:
        print(f"plot_client_accuracy_individual: nenhum server_metrics.json em {metrics_dir}")
        return

    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  [WARN] falha ao ler {f}: {e}")
            continue

        rounds = data.get("rounds", [])
        train_rounds = [r for r in rounds if r.get("round", 0) > 0]
        if not train_rounds:
            continue

        num_clients = int(train_rounds[0].get("num_clients", 0)) or len(
            train_rounds[0].get("client_metrics", []) or []
        )
        if num_clients <= 0:
            continue

        # client_id → (rounds, accs)
        per_client: dict = {}
        for r in train_rounds:
            for cm in r.get("client_metrics", []) or []:
                cid = cm.get("node_id", cm.get("client_id", cm.get("client_index", "?")))
                acc = cm.get("accuracy")
                if acc is None:
                    continue
                per_client.setdefault(cid, {"rounds": [], "accs": []})
                per_client[cid]["rounds"].append(r["round"])
                per_client[cid]["accs"].append(acc)

        if not per_client:
            continue

        fig, ax = plt.subplots(figsize=(6, 4))
        for cid in sorted(per_client.keys(), key=lambda k: str(k)):
            v = per_client[cid]
            ax.plot(v["rounds"], v["accs"], marker="o", linewidth=2, label=f"Client {cid}")
        ax.set_xlabel("Round")
        ax.set_ylabel("Accuracy")
        ax.set_title(f"Client accuracy (N={num_clients})")
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        ax.xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
        ax.legend(loc="upper left", bbox_to_anchor=(1.05, 1), fontsize=8, borderaxespad=0.0)

        out_path = out_base / f"accuracy_n{num_clients}_clients.png"
        _save(fig, str(out_path))


def plot_ablation(summary_file, output_prefix=""):
    """Plot do estudo de ablação: tempo médio por round e gas total por modo.

    Gera:
      - ``{output_prefix}plot_ablation_time.png``: barras horizontais de
        ``mean_round_time_s`` por modo.
      - ``{output_prefix}plot_ablation_gas.png``: barras de ``total_gas_eth``
        por modo (baseline=0 como referência).
    """
    path = Path(summary_file)
    if not path.exists():
        print(f"plot_ablation: {summary_file} não encontrado")
        return

    with open(path) as f:
        summary = json.load(f)

    results = summary.get("results", {})
    if not results:
        print("plot_ablation: 'results' vazio")
        return

    order = [m for m in ("baseline", "no_ipfs", "full") if m in results]
    times = [float(results[m].get("mean_round_time_s", 0.0)) for m in order]
    gases = [float(results[m].get("total_gas_eth", 0.0)) for m in order]

    color_for = {
        "baseline": PLOT_PALETTE["baseline"],
        "no_ipfs":  PLOT_PALETTE["malicious"],
        "full":     PLOT_PALETTE["full"],
    }
    bar_colors = [color_for.get(m, PLOT_PALETTE["gas"]) for m in order]

    # ---- Tempo médio por round (horizontal) ----
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.barh(order, times, color=bar_colors)
    ax.set_xlabel("Mean round time (s)")
    ax.set_title("Ablation: tempo médio por round por modo")
    for i, v in enumerate(times):
        ax.text(v, i, f" {v:.2f}s", va="center")
    out_time = f"{output_prefix}plot_ablation_time.png"
    _save(fig, out_time)

    # ---- Gas total ----
    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    ax.bar(order, gases, color=bar_colors)
    ax.set_ylabel("Total gas (ETH)")
    ax.set_title("Ablation: custo total de gas por modo")
    for i, v in enumerate(gases):
        ax.text(i, v, f"{v:.6f}", ha="center", va="bottom", fontsize=9)
    out_gas = f"{output_prefix}plot_ablation_gas.png"
    _save(fig, out_gas)
    print(f"Generated: {out_time}, {out_gas}")


if __name__ == "__main__":
    Path("results/figures").mkdir(parents=True, exist_ok=True)
    plot_metrics_publishable()

    if Path("results/baseline_metrics.json").exists():
        plot_baseline_comparison(
            "results/server_metrics.json",
            "results/baseline_metrics.json",
            output_prefix=""
        )
    if Path("results/multi_run/summary.json").exists():
        plot_multi_run_summary("results/multi_run/summary.json", output_prefix="")
    if Path("results/server_metrics_breakdown.json").exists():
        plot_gas_breakdown("results/server_metrics_breakdown.json", output_prefix="")
    if Path("results/server_metrics.json").exists():
        plot_update_norms("results/server_metrics.json", output_prefix="")
    if Path("results/security/security_summary.json").exists():
        plot_security_summary("results/security/security_summary.json", output_prefix="")
    if Path("results/multi_run").exists():
        plot_client_accuracy_individual("results/multi_run", "results/figures")
    if Path("results/ablation/ablation_summary.json").exists():
        plot_ablation("results/ablation/ablation_summary.json", output_prefix="")
