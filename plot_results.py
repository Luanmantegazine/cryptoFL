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
