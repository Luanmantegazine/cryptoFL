"""
Plota os resultados dos experimentos do CryptoFL a partir dos arquivos JSON
gerados em results/. Gera:
  - Scaling: acuracia e tempo vs numero de clientes (fedavg vs fedprox)
  - Seguranca: acuracia final e queda de acuracia vs % de clientes maliciosos
  - Ablacao: acuracia final por modo

Saida: PNGs em results/figures_summary/
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    plt.style.use("seaborn-v0_8-darkgrid")
except OSError:
    plt.style.use("ggplot")

plt.rcParams.update({
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 10,
    "figure.dpi": 130,
})

RESULTS = Path("results")
OUT = RESULTS / "figures_summary"
OUT.mkdir(parents=True, exist_ok=True)


def load(path):
    p = Path(path)
    if not p.exists():
        print(f"[skip] nao encontrado: {p}")
        return None
    with open(p) as f:
        return json.load(f)


def plot_scaling(summary_path):
    data = load(summary_path)
    if data is None:
        return
    results = data["results"]
    aggregators = data["config"].get("aggregators", ["fedavg", "fedprox"])
    clients = sorted(int(c) for c in results)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    for agg in aggregators:
        acc, acc_std, t, t_std = [], [], [], []
        for c in clients:
            r = results[str(c)].get(agg, {})
            acc.append(r.get("mean_accuracy", np.nan))
            acc_std.append(r.get("std_accuracy", 0))
            t.append(r.get("mean_time_s", np.nan))
            t_std.append(r.get("std_time_s", 0))
        ax1.errorbar(clients, acc, yerr=acc_std, marker="o", capsize=4, label=agg)
        ax2.errorbar(clients, t, yerr=t_std, marker="s", capsize=4, label=agg)

    ax1.set_title("Acuracia vs Numero de Clientes")
    ax1.set_xlabel("Numero de clientes")
    ax1.set_ylabel("Acuracia final")
    ax1.set_xticks(clients)
    ax1.legend()

    ax2.set_title("Tempo de treino vs Numero de Clientes")
    ax2.set_xlabel("Numero de clientes")
    ax2.set_ylabel("Tempo (s)")
    ax2.set_xticks(clients)
    ax2.legend()

    fig.suptitle("Experimento de Escalabilidade (MNIST)", fontsize=15)
    fig.tight_layout()
    out = OUT / "scaling_overview.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_security(summary_path):
    data = load(summary_path)
    if data is None:
        return
    results = data["results"]
    pcts = sorted(float(p) for p in results)
    labels = [f"{int(p*100)}%" for p in pcts]
    final_acc = [results[str(p)]["final_accuracy"] for p in pcts]
    acc_drop = [results[str(p)]["accuracy_drop"] for p in pcts]
    acc_std = [results[str(p)].get("std_final_accuracy", 0) for p in pcts]
    drop_std = [results[str(p)].get("std_accuracy_drop", 0) for p in pcts]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    x = np.arange(len(pcts))

    ax1.bar(x, final_acc, yerr=acc_std, capsize=4, color="#2a9d8f")
    ax1.set_title("Acuracia final vs Clientes maliciosos")
    ax1.set_xlabel("% de clientes maliciosos")
    ax1.set_ylabel("Acuracia final")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)

    ax2.bar(x, acc_drop, yerr=drop_std, capsize=4, color="#e76f51")
    ax2.set_title("Queda de acuracia vs Clientes maliciosos")
    ax2.set_xlabel("% de clientes maliciosos")
    ax2.set_ylabel("Queda de acuracia")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)

    attack = data["config"].get("attack_type", "")
    fig.suptitle(f"Experimento de Seguranca (ataque: {attack})", fontsize=15)
    fig.tight_layout()
    out = OUT / "security_overview.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_ablation(summary_path):
    data = load(summary_path)
    if data is None:
        return
    results = data["results"]
    modes = list(results)
    acc = [results[m].get("final_accuracy", np.nan) for m in modes]
    times = [results[m].get("mean_round_time_s", np.nan) for m in modes]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    x = np.arange(len(modes))
    ax1.bar(x, acc, color="#264653")
    ax1.set_title("Acuracia final por modo")
    ax1.set_ylabel("Acuracia final")
    ax1.set_xticks(x)
    ax1.set_xticklabels(modes)

    ax2.bar(x, times, color="#e9c46a")
    ax2.set_title("Tempo medio por round")
    ax2.set_ylabel("Tempo (s)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(modes)

    fig.suptitle("Experimento de Ablacao", fontsize=15)
    fig.tight_layout()
    out = OUT / "ablation_overview.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_accuracy_curves():
    """Curvas de acuracia por round para todos os baseline_metrics encontrados."""
    files = sorted(RESULTS.rglob("baseline_metrics.json"))
    curves = []
    for f in files:
        d = load(f)
        if not d:
            continue
        hist = d.get("accuracy_history")
        if not hist:
            rounds = d.get("rounds", [])
            hist = [r.get("accuracy") for r in rounds if r.get("accuracy") is not None]
        if hist:
            label = f.parent.name
            curves.append((label, hist))
    if not curves:
        return
    # limita a 12 curvas para legibilidade
    curves = curves[:12]
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, hist in curves:
        ax.plot(range(1, len(hist) + 1), hist, marker="o", label=label)
    ax.set_title("Curvas de acuracia por round")
    ax.set_xlabel("Round")
    ax.set_ylabel("Acuracia")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    out = OUT / "accuracy_curves.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


if __name__ == "__main__":
    plot_scaling(RESULTS / "scaling_mnist_rep3" / "scaling_summary.json")
    plot_security(RESULTS / "security_test2" / "security_summary.json")
    plot_ablation(RESULTS / "ablation_test" / "ablation_summary.json")
    plot_accuracy_curves()
    print(f"\nFiguras geradas em: {OUT}/")
