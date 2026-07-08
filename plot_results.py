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


def _round_breakdown_stages(language="pt"):
    if language == "en":
        return [
            ("matching_time_s", "Matching", "#4C6A92"),
            ("download_model_time_s", "Model Download", "#5FA8D3"),
            ("local_training_time_s", "Local Training", "#1B9E77"),
            ("upload_ipfs_time_s", "IPFS Upload", "#F4A261"),
            ("blockchain_tx_time_s", "Blockchain Tx", "#E76F51"),
            ("aggregation_time_s", "Aggregation", "#264653"),
            ("publish_global_model_time_s", "Global Model Publish", "#A8DADC"),
        ]
    return [
        ("matching_time_s", "Matching", "#4C6A92"),
        ("download_model_time_s", "Download modelo", "#5FA8D3"),
        ("local_training_time_s", "Treinamento local", "#1B9E77"),
        ("upload_ipfs_time_s", "Upload IPFS", "#F4A261"),
        ("blockchain_tx_time_s", "Transacao blockchain", "#E76F51"),
        ("aggregation_time_s", "Agregacao", "#264653"),
        ("publish_global_model_time_s", "Publicacao modelo global", "#A8DADC"),
    ]


def plot_round_time_breakdown(metrics_file="results/server_metrics.json", language="pt"):
    path = Path(metrics_file)
    if not path.exists():
        path = Path("server_metrics.json")
        if not path.exists():
            print(f"Error: File '{metrics_file}' not found.")
            return

    with open(path) as f:
        data = json.load(f)

    rounds = [r for r in data.get("rounds", []) if r.get("round", 0) > 0]
    if not rounds:
        print("Warning: No training rounds found for time breakdown.")
        return

    stages = _round_breakdown_stages(language=language)

    per_round = []
    sums = {k: 0.0 for k, _, _ in stages}
    for r in rounds:
        row = {"round": int(r.get("round", 0))}
        for key, _, _ in stages:
            value = r.get(key)
            if value is None and key == "local_training_time_s":
                value = r.get("train_time_round_s")
            try:
                row[key] = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                row[key] = 0.0
            sums[key] += row[key]
        total = r.get("round_total_time_s")
        if total is None:
            total = sum(row[k] for k, _, _ in stages)
        row["round_total_time_s"] = float(total)
        per_round.append(row)

    n = len(per_round)
    means = {k: (sums[k] / n) for k, _, _ in stages}
    total_mean = sum(means.values())
    if total_mean <= 0:
        print("Warning: Round total time is zero; skipping time breakdown plot.")
        return

    fig, ax = plt.subplots(figsize=(12, 2.4))
    left = 0.0
    for key, label, color in stages:
        t = means[key]
        if t <= 0:
            continue
        pct = 100.0 * t / total_mean
        ax.barh([0], [t], left=left, color=color, edgecolor="white", height=0.55)
        text = f"{label} ({pct:.1f}%)"
        if pct >= 5.0:
            ax.text(left + t / 2, 0, text, ha="center", va="center", fontsize=9, color="white")
        left += t

    if language == "en":
        ax.set_title(f"Round Time Breakdown (mean of {n} rounds)")
        ax.set_xlabel("Time (s)")
    else:
        ax.set_title(f"Tempo do round (media de {n} rounds)")
        ax.set_xlabel("Tempo (s)")
    ax.set_yticks([])

    legend_handles = []
    legend_labels = []
    for key, label, color in stages:
        t = means[key]
        if t <= 0:
            continue
        pct = 100.0 * t / total_mean
        legend_handles.append(plt.Rectangle((0, 0), 1, 1, color=color))
        legend_labels.append(f"{label}: {t:.3f}s ({pct:.1f}%)")
    ax.legend(legend_handles, legend_labels, loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=2, frameon=False)

    plt.tight_layout()

    out_dir = path.parent if path.parent != Path(".") else Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / ("round_time_breakdown_en.png" if language == "en" else "round_time_breakdown.png")
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close()

    out_json = out_dir / ("round_time_breakdown_en.json" if language == "en" else "round_time_breakdown.json")
    payload = {
        "source_metrics": str(path),
        "n_rounds": n,
        "mean_stage_time_s": means,
        "mean_total_time_s": total_mean,
        "rounds": per_round,
    }
    out_json.write_text(json.dumps(payload, indent=2))

    print(f"  {out_png.name}")
    print(f"  {out_json.name}")


def plot_round_time_breakdown_scaling(raw_root="results/e2e_scaling/raw", rounds_min=1, language="en"):
    raw_dir = Path(raw_root)
    if not raw_dir.exists():
        print(f"Error: Directory '{raw_root}' not found.")
        return

    stages = _round_breakdown_stages(language=language)
    stage_keys = [k for k, _, _ in stages]
    stage_labels = {k: lbl for k, lbl, _ in stages}
    stage_colors = {k: color for k, _, color in stages}

    clients_list = []
    means_by_stage = {k: [] for k in stage_keys}

    for run_dir in sorted(raw_dir.glob("n*_rep*")):
        metrics_path = run_dir / "server_metrics.json"
        if not metrics_path.exists():
            continue

        with open(metrics_path) as f:
            data = json.load(f)

        rounds = [r for r in data.get("rounds", []) if r.get("round", 0) > 0]
        if len(rounds) < rounds_min:
            continue

        clients = None
        for r in rounds:
            n_clients = r.get("num_clients")
            if n_clients is not None:
                clients = int(n_clients)
                break
        if clients is None:
            try:
                clients = int(run_dir.name.split("_")[0].replace("n", ""))
            except Exception:
                continue

        sums = {k: 0.0 for k in stage_keys}
        for r in rounds:
            for key in stage_keys:
                value = r.get(key)
                if value is None and key == "local_training_time_s":
                    value = r.get("train_time_round_s")
                try:
                    sums[key] += float(value) if value is not None else 0.0
                except (TypeError, ValueError):
                    pass

        n = len(rounds)
        clients_list.append(clients)
        for key in stage_keys:
            means_by_stage[key].append(sums[key] / n if n > 0 else 0.0)

    if not clients_list:
        print("Warning: No valid scaling runs found for breakdown comparison.")
        return

    order = sorted(range(len(clients_list)), key=lambda i: clients_list[i])
    clients_list = [clients_list[i] for i in order]
    for key in stage_keys:
        means_by_stage[key] = [means_by_stage[key][i] for i in order]

    fig, ax = plt.subplots(figsize=(12, 5))
    bottom = [0.0] * len(clients_list)

    for key in stage_keys:
        values = means_by_stage[key]
        ax.bar(
            [str(c) for c in clients_list],
            values,
            bottom=bottom,
            color=stage_colors[key],
            edgecolor="white",
            label=stage_labels[key],
        )
        bottom = [b + v for b, v in zip(bottom, values)]

    if language == "en":
        ax.set_title("End-to-End Round Time by Number of Clients")
        ax.set_xlabel("Number of clients")
        ax.set_ylabel("Mean round time (s)")
    else:
        ax.set_title("Tempo de round fim-a-fim por numero de clientes")
        ax.set_xlabel("Numero de clientes")
        ax.set_ylabel("Tempo medio por round (s)")

    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
    plt.tight_layout()

    out_dir = Path("results/e2e_scaling")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / ("round_time_breakdown_scaling_en.png" if language == "en" else "round_time_breakdown_scaling.png")
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close()

    payload = {
        "clients": clients_list,
        "mean_stage_time_s": means_by_stage,
        "language": language,
        "rounds_min": rounds_min,
        "source_root": str(raw_dir),
    }
    out_json = out_dir / ("round_time_breakdown_scaling_en.json" if language == "en" else "round_time_breakdown_scaling.json")
    out_json.write_text(json.dumps(payload, indent=2))

    print(f"  {out_png.name}")
    print(f"  {out_json.name}")


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
    gas_fees = [r["gas_eth"] for r in train_rounds]
    num_clients = [r["num_clients"] for r in train_rounds]
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
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, gas_fees, marker="o", linewidth=2, color="#1f77b4")
    plt.xlabel("Round")
    plt.ylabel("Gas (ETH)")
    plt.title("Gas Cost per Round")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_gas_per_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 2 – Cumulative Gas
    # ------------------------------
    cumulative = [sum(gas_fees[: i + 1]) for i in range(len(gas_fees))]
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, cumulative, marker="s", linewidth=2, color="#ff7f0e")
    plt.xlabel("Round")
    plt.ylabel("Cumulative Gas (ETH)")
    plt.title("Cumulative Gas Consumption")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_cumulative_gas.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 3 – Gas Per Client
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, gas_per_client, marker="^", linewidth=2, color="#2ca02c")
    plt.xlabel("Round")
    plt.ylabel("Gas per Client (ETH)")
    plt.title("Gas Cost Per Client")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_gas_per_client.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 4 – Avg Loss per Round
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, round_avg_loss, marker="o", linewidth=2, color="#d62728")
    plt.xlabel("Round")
    plt.ylabel("Average Loss")
    plt.title("Average Client Loss per Round")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_avg_loss_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 5 – Avg Training Time per Round
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, round_avg_train_time, marker="o", linewidth=2, color="#9467bd")
    plt.xlabel("Round")
    plt.ylabel("Average Training Time (s)")
    plt.title("Training Time per Round")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_train_time_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 6 – Total Examples per Round
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, round_avg_loss, marker="o", linewidth=2, color="#d62728")
    plt.xlabel("Round")
    plt.ylabel("Total Training Examples")
    plt.title("Total Examples Processed per Round")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_total_examples_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 7 – Global Accuracy per Round
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, round_accuracy, marker="o", linewidth=2, color="#e377c2")
    plt.xlabel("Round")
    plt.ylabel("Accuracy")
    plt.title("Global Accuracy per Round")
    plt.gca().yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_accuracy_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 8 – Global Loss per Round
    # ------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(rounds, round_loss, marker="o", linewidth=2, color="#7f7f7f")
    plt.xlabel("Round")
    plt.ylabel("Loss")
    plt.title("Global Loss per Round")
    plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig("plot_loss_round.png", dpi=300)
    plt.close()

    # ------------------------------
    # PLOT 9 – Client Accuracy per Round
    # ------------------------------
    if client_accuracy_by_round:
        plt.figure(figsize=(9, 6))
        for node_id, values in sorted(client_accuracy_by_round.items()):
            plt.plot(
                values["rounds"],
                values["accuracy"],
                marker="o",
                linewidth=2,
                label=f"Client {node_id}",
            )
        plt.xlabel("Round")
        plt.ylabel("Accuracy")
        plt.title("Client Accuracy per Round")
        plt.legend()
        plt.gca().yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        plt.gca().xaxis.set_major_locator(mtick.MaxNLocator(integer=True))
        plt.tight_layout()
        plt.savefig("plot_client_accuracy_round.png", dpi=300)
        plt.close()

    print("Generated:")
    print("  plot_gas_per_round.png")
    print("  plot_cumulative_gas.png")
    print("  plot_gas_per_client.png")
    print("  plot_avg_loss_round.png")
    print("  plot_train_time_round.png")
    print("  plot_total_examples_round.png")
    print("  plot_accuracy_round.png")
    print("  plot_loss_round.png")
    if client_accuracy_by_round:
        print("  plot_client_accuracy_round.png")


if __name__ == "__main__":
    plot_metrics_publishable()
    plot_round_time_breakdown()
