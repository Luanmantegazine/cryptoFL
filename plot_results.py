import json
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from pathlib import Path

# Style Configuration (Academic & Clean)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({'font.size': 12, 'font.family': 'sans-serif'})


def plot_metrics_publishable(metrics_file="results/server_metrics.json"):
    # 1. Load data safely
    path = Path(metrics_file)
    if not path.exists():
        # Try root folder if not found in results
        path = Path("server_metric.json")
        if not path.exists():
            print(f"❌ Error: File '{metrics_file}' not found.")
            return

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Error: File '{metrics_file}' is not valid JSON.")
        return

    # 2. Filter data (Ignoring Round 0 - Deploy/Setup)
    all_rounds = data.get('rounds', [])
    rounds = [r['round'] for r in all_rounds if r['round'] > 0]

    if not rounds:
        print("⚠️  Warning: No completed training rounds found.")
        return

    gas_fees = [r['gas_eth'] for r in all_rounds if r['round'] > 0]
    num_clients = [r['num_clients'] for r in all_rounds if r['round'] > 0]

    # New Metric: Gas consumed per client (Aggregation Efficiency)
    # Calculates how much it cost the server to process each individual client contribution
    gas_per_client = [g / n if n > 0 else 0 for g, n in zip(gas_fees, num_clients)]

    # Define client count for title
    client_count_str = str(num_clients[1]) if num_clients else "?"

    # Create Subplots (2x2)
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(
        f'Federated Learning Performance via Arbitrum Sepolia\n(Scenario: {len(rounds)} Rounds, {client_count_str} Clients)',
        fontsize=16, fontweight='bold', y=0.98)

    # ---------------------------------------------------------
    # Plot 1: Gas Cost per Round (Total Aggregation)
    # ---------------------------------------------------------
    ax1 = axes[0, 0]
    color = '#2980b9'
    ax1.plot(rounds, gas_fees, marker='o', linestyle='-', linewidth=2, color=color)
    ax1.set_xlabel('Training Round', fontweight='bold')
    ax1.set_ylabel('Gas Fee (ETH)', fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Total Aggregation Cost (Server)', fontsize=14)

    # Scientific notation for small ETH values
    ax1.yaxis.set_major_formatter(mtick.ScalarFormatter(useMathText=True))

    # ---------------------------------------------------------
    # Plot 2: Total Cumulative Cost
    # ---------------------------------------------------------
    cumulative_gas = [sum(gas_fees[:i + 1]) for i in range(len(gas_fees))]
    ax2 = axes[0, 1]
    ax2.fill_between(rounds, cumulative_gas, color='#e74c3c', alpha=0.1)
    ax2.plot(rounds, cumulative_gas, marker='s', linewidth=2, color='#c0392b')
    ax2.set_xlabel('Training Round', fontweight='bold')
    ax2.set_ylabel('Cumulative Gas (ETH)', fontweight='bold')
    ax2.set_title('Total Training Cost (Cumulative)', fontsize=14)

    # Final value annotation
    final_cost = cumulative_gas[-1]
    ax2.annotate(f'Total: {final_cost:.6f} ETH',
                 xy=(rounds[-1], final_cost),
                 xytext=(-60, 10), textcoords='offset points',
                 arrowprops=dict(arrowstyle="->", color='black'),
                 fontsize=10, fontweight='bold')
    ax2.yaxis.set_major_formatter(mtick.ScalarFormatter(useMathText=True))

    # ---------------------------------------------------------
    # Plot 3: Gas Consumption per Client (Efficiency)
    # ---------------------------------------------------------
    ax3 = axes[1, 0]
    color_client = '#8e44ad'
    ax3.plot(rounds, gas_per_client, marker='^', linestyle='--', linewidth=2, color=color_client)
    ax3.set_xlabel('Training Round', fontweight='bold')
    ax3.set_ylabel('Gas / Client (ETH)', fontweight='bold')
    ax3.set_title('Average Cost per Client (Efficiency)', fontsize=14)
    ax3.grid(True, alpha=0.3)

    # Highlight Mean
    avg_gas_client = sum(gas_per_client) / len(gas_per_client) if len(gas_per_client) > 0 else 0
    ax3.axhline(y=avg_gas_client, color='gray', linestyle=':', alpha=0.8, label=f'Mean: {avg_gas_client:.2e} ETH')
    ax3.legend(loc='upper right')
    ax3.yaxis.set_major_formatter(mtick.ScalarFormatter(useMathText=True))

    # ---------------------------------------------------------
    # 4. Technical Summary (ETH Only)
    # ---------------------------------------------------------
    axes[1, 1].axis('off')

    avg_gas = sum(gas_fees) / len(gas_fees) if gas_fees else 0
    max_clients = max(num_clients) if num_clients else 0

    # Stability calculation
    var_gas = ((max(gas_fees) - min(gas_fees)) / avg_gas * 100) if avg_gas > 0 else 0

    # Time handling
    start_time = data.get('experiment_start', 'N/A').split('T')[1][:8]
    end_time_raw = data.get('experiment_end', 'Ongoing')
    end_time = end_time_raw.split('T')[1][:8] if 'T' in end_time_raw else 'Ongoing'

    summary_text = f"""
    📊 TECHNICAL RESULTS (ETH Only)
    ──────────────────────────────

    ⏱️ EXECUTION
       • Start: {start_time}
       • End:   {end_time}

    💰 TOTAL COST (L2)
       • Total ({len(rounds)} Rounds): {final_cost:.8f} ETH
       • Avg per Round: {avg_gas:.8f} ETH

    ⚡ EFFICIENCY
       • Avg Cost/Client: {avg_gas_client:.8f} ETH
       • Concurrent Clients: {max_clients}
       • Cost Variation: {var_gas:.2f}% 

    🔗 INFRASTRUCTURE
       • Network: Arbitrum Sepolia
       • Contract: {data.get('job_addresses', ['?'])[0][:10]}...
    """

    axes[1, 1].text(0.05, 0.5, summary_text, fontsize=12, family='monospace',
                    verticalalignment='center', bbox=dict(boxstyle="round,pad=1", fc="#ecf0f1", ec="#bdc3c7"))

    plt.tight_layout()
    output_file = "experiment_results_eth_only.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Plot successfully generated: {output_file}")
    plt.show()


if __name__ == "__main__":
    plot_metrics_publishable()