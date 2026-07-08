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
    cfg = data.get("config", {})
    aggregators = cfg.get("aggregators", ["fedavg", "fedprox"])
    clients = sorted(int(c) for c in results)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(17, 5))
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
        # Variancia do treino: desvio-padrao da acuracia entre as reps.
        ax3.plot(clients, acc_std, marker="^", label=agg)

    ax1.set_title("Accuracy vs Number of Clients")
    ax1.set_xlabel("Number of clients")
    ax1.set_ylabel("Final accuracy (mean ± std)")
    ax1.set_xticks(clients)
    ax1.legend()

    ax2.set_title("Training time vs Number of Clients")
    ax2.set_xlabel("Number of clients")
    ax2.set_ylabel("Time (s) (mean ± std)")
    ax2.set_xticks(clients)
    ax2.legend()

    ax3.set_title("Training variance (std of accuracy)")
    ax3.set_xlabel("Number of clients")
    ax3.set_ylabel("Std of final accuracy")
    ax3.set_xticks(clients)
    ax3.legend()

    reps = cfg.get("repetitions", cfg.get("reps", "?"))
    fig.suptitle(f"Scalability Experiment (MNIST, {reps} reps)", fontsize=15)
    fig.tight_layout()
    out = OUT / "scaling_overview.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")

    # Salva paineis separados para uso no paper.
    fig_a, ax_a = plt.subplots(figsize=(7.0, 4.2))
    for agg in aggregators:
        acc, acc_std = [], []
        for c in clients:
            r = results[str(c)].get(agg, {})
            acc.append(r.get("mean_accuracy", np.nan))
            acc_std.append(r.get("std_accuracy", 0))
        ax_a.errorbar(clients, acc, yerr=acc_std, marker="o", capsize=4, label=agg)
    ax_a.set_title("Accuracy vs Number of Clients")
    ax_a.set_xlabel("Number of clients")
    ax_a.set_ylabel("Final accuracy (mean ± std)")
    ax_a.set_xticks(clients)
    ax_a.legend()
    fig_a.tight_layout()
    out_a = OUT / "scaling_overview_accuracy.png"
    fig_a.savefig(out_a, bbox_inches="tight")
    plt.close(fig_a)
    print(f"[ok] {out_a}")

    fig_t, ax_t = plt.subplots(figsize=(7.0, 4.2))
    for agg in aggregators:
        t, t_std = [], []
        for c in clients:
            r = results[str(c)].get(agg, {})
            t.append(r.get("mean_time_s", np.nan))
            t_std.append(r.get("std_time_s", 0))
        ax_t.errorbar(clients, t, yerr=t_std, marker="s", capsize=4, label=agg)
    ax_t.set_title("Training time vs Number of Clients")
    ax_t.set_xlabel("Number of clients")
    ax_t.set_ylabel("Time (s) (mean ± std)")
    ax_t.set_xticks(clients)
    ax_t.legend()
    fig_t.tight_layout()
    out_t = OUT / "scaling_overview_time.png"
    fig_t.savefig(out_t, bbox_inches="tight")
    plt.close(fig_t)
    print(f"[ok] {out_t}")

    fig_v, ax_v = plt.subplots(figsize=(7.0, 4.2))
    for agg in aggregators:
        acc_std = []
        for c in clients:
            r = results[str(c)].get(agg, {})
            acc_std.append(r.get("std_accuracy", 0))
        ax_v.plot(clients, acc_std, marker="^", label=agg)
    ax_v.set_title("Training variance (std of accuracy)")
    ax_v.set_xlabel("Number of clients")
    ax_v.set_ylabel("Std of final accuracy")
    ax_v.set_xticks(clients)
    ax_v.legend()
    fig_v.tight_layout()
    out_v = OUT / "scaling_overview_variance.png"
    fig_v.savefig(out_v, bbox_inches="tight")
    plt.close(fig_v)
    print(f"[ok] {out_v}")


def plot_security(summary_path, attack_label=None, out_name=None):
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
    flagged = [
        results[str(p)].get(
            "mean_n_flagged_per_run",
            results[str(p)].get("n_flagged_total", 0),
        )
        for p in pcts
    ]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))
    x = np.arange(len(pcts))

    ax1.bar(x, final_acc, yerr=acc_std, capsize=4, color="#2a9d8f")
    ax1.set_title("Final accuracy vs Malicious clients")
    ax1.set_xlabel("% of malicious clients")
    ax1.set_ylabel("Final accuracy")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)

    ax2.bar(x, acc_drop, yerr=drop_std, capsize=4, color="#e76f51")
    ax2.set_title("Accuracy drop vs Malicious clients")
    ax2.set_xlabel("% of malicious clients")
    ax2.set_ylabel("Accuracy drop")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)

    ax3.bar(x, flagged, color="#577590")
    ax3.set_title("Flagged updates vs Malicious clients")
    ax3.set_xlabel("% of malicious clients")
    ax3.set_ylabel("Flagged updates")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels)

    attack = attack_label or data["config"].get("attack_type", "")
    fig.suptitle(f"Security Experiment (attack: {attack})", fontsize=15)
    fig.tight_layout()
    out = OUT / (out_name or f"security_overview_{attack}.png")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_security_detector_comparison(scaling_summary_path, noise_summary_path, labelflip_summary_path):
    scaling_data = load(scaling_summary_path)
    noise_data = load(noise_summary_path)
    labelflip_data = load(labelflip_summary_path)
    if scaling_data is None or noise_data is None or labelflip_data is None:
        return

    scaling_results = scaling_data["results"]
    noise_results = noise_data["results"]
    lf_results = labelflip_data["results"]
    pcts = sorted(
        set(float(p) for p in scaling_results)
        & set(float(p) for p in noise_results)
        & set(float(p) for p in lf_results)
    )
    if not pcts:
        print("[skip] sem interseccao de fracoes entre summaries de seguranca")
        return

    labels = [f"{int(p*100)}%" for p in pcts]
    scaling_flagged = [
        scaling_results[str(p)].get(
            "mean_n_flagged_per_run",
            scaling_results[str(p)].get("n_flagged_total", 0),
        )
        for p in pcts
    ]
    noise_flagged = [
        noise_results[str(p)].get(
            "mean_n_flagged_per_run",
            noise_results[str(p)].get("n_flagged_total", 0),
        )
        for p in pcts
    ]
    lf_flagged = [
        lf_results[str(p)].get(
            "mean_n_flagged_per_run",
            lf_results[str(p)].get("n_flagged_total", 0),
        )
        for p in pcts
    ]

    x = np.arange(len(pcts))
    w = 0.25
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - w, scaling_flagged, width=w, label="scaling", color="#264653")
    ax.bar(x, noise_flagged, width=w, label="noise", color="#2a9d8f")
    ax.bar(x + w, lf_flagged, width=w, label="label_flip", color="#e76f51")
    ax.set_title("Detector comparison: scaling vs noise vs label_flip")
    ax.set_xlabel("% of malicious clients")
    ax.set_ylabel("Flagged updates")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    fig.tight_layout()
    out = OUT / "security_detector_comparison.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_ksens(summary_path):
    data = load(summary_path)
    if data is None:
        return

    rows = data.get("rows", [])
    if not rows:
        print("[skip] ksens sem linhas")
        return

    rows = sorted(rows, key=lambda r: float(r["k"]))
    ks = [float(r["k"]) for r in rows]
    attack_flagged = [float(r.get("attack_flagged", 0.0)) for r in rows]
    clean_false_pos = [float(r.get("clean_false_pos", 0.0)) for r in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ks, attack_flagged, marker="o", linewidth=2, label="attack_flagged")
    ax.plot(ks, clean_false_pos, marker="s", linewidth=2, label="clean_false_pos")
    ax.set_title("k-sensitivity (noise @20% vs clean @0%)")
    ax.set_xlabel("k (NORM_THRESHOLD_STD)")
    ax.set_ylabel("Flagged updates (total)")
    ax.set_xticks(ks)
    ax.legend()

    fig.tight_layout()
    out = OUT / "ksens.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_ablation(summary_path):
    data = load(summary_path)
    if data is None:
        return
    results = data["results"]
    label_map = {
        "baseline": "baseline\n(Flower puro)",
        "no_ipfs": "no-IPFS\n(on-chain)",
        "full": "full\n(on-chain+IPFS)",
    }
    modes = list(results)
    labels = [label_map.get(m, m) for m in modes]
    acc = [results[m].get("final_accuracy", np.nan) for m in modes]
    acc_std = [results[m].get("std_final_accuracy", 0.0) for m in modes]
    times = [results[m].get("mean_round_time_s", np.nan) for m in modes]
    times_std = [results[m].get("std_round_time_s", 0.0) for m in modes]
    gas = [results[m].get("total_gas_eth", 0.0) for m in modes]
    gas_std = [results[m].get("std_total_gas_eth", 0.0) for m in modes]

    def _annotate(ax, values, errs, fmt):
        for i, (v, e) in enumerate(zip(values, errs)):
            ax.text(i, v + (e or 0.0), fmt.format(v), ha="center", va="bottom", fontsize=9)

    def _annotate_h(ax, yvals, xvals, xerrs, fmt):
        xmin, xmax = ax.get_xlim()
        xspan = xmax - xmin
        offset = 0.015 * xspan if xspan > 0 else 0.05
        for y, xval, xerr in zip(yvals, xvals, xerrs):
            ax.text(xval + (xerr or 0.0) + offset, y, fmt.format(xval), va="center", fontsize=9)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))
    x = np.arange(len(modes))

    # Tempo: dot-plot com barras de erro (mais legível que barras para diferenças pequenas).
    order = np.argsort(times)
    times_s = [times[i] for i in order]
    times_std_s = [times_std[i] for i in order]
    labels_s = [labels[i] for i in order]
    y = np.arange(len(times_s))

    ax1.errorbar(
        times_s,
        y,
        xerr=times_std_s,
        fmt="o",
        color="#e9c46a",
        ecolor="#c98b1d",
        elinewidth=2,
        capsize=4,
        markersize=7,
    )
    ax1.set_title("Mean time per round (overhead)")
    ax1.set_xlabel("Time (s)")
    ax1.set_yticks(y)
    ax1.set_yticklabels(labels_s)
    baseline_time = results.get("baseline", {}).get("mean_round_time_s")
    if baseline_time is not None:
        ax1.axvline(baseline_time, color="#6c757d", linestyle="--", linewidth=1.3, alpha=0.8)
    t_min = min((v - e) for v, e in zip(times_s, times_std_s)) if times_s else 0
    t_max = max((v + e) for v, e in zip(times_s, times_std_s)) if times_s else 1
    pad = max((t_max - t_min) * 0.2, 0.4)
    ax1.set_xlim(max(0.0, t_min - pad), t_max + pad)
    ax1.grid(axis="x", alpha=0.25, linestyle=":")
    _annotate_h(ax1, y, times_s, times_std_s, "{:.1f}s")

    # Gás é determinístico -> std ~ 0 (barras de erro mostradas mesmo assim).
    ax2.bar(x, gas, yerr=gas_std, capsize=5, color="#e76f51")
    ax2.set_title("Total gas cost")
    ax2.set_ylabel("Gas (ETH)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylim(0, max(gas) * 1.25 if max(gas) > 0 else 1)
    _annotate(ax2, gas, gas_std, "{:.2e}")

    ax3.bar(x, acc, yerr=acc_std, capsize=5, color="#264653")
    ax3.set_title("Final accuracy per mode")
    ax3.set_ylabel("Final accuracy")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels)
    ax3.set_ylim(0, 1.05)
    _annotate(ax3, acc, acc_std, "{:.4f}")

    cfg = data.get("config", {})
    reps = cfg.get("repetitions", "?")
    subtitle = (f"Ablation Experiment (N={cfg.get('clients', '?')}, "
                f"rounds={cfg.get('rounds', '?')}, {reps} reps, mean ± std)")
    fig.suptitle(subtitle, fontsize=15)
    fig.tight_layout()
    out = OUT / "ablation_overview.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")

    # Salva paineis separados (tempo/gas/acuracia) para uso no paper.
    fig_t, ax_t = plt.subplots(figsize=(6.8, 4.2))
    ax_t.errorbar(
        times_s,
        y,
        xerr=times_std_s,
        fmt="o",
        color="#e9c46a",
        ecolor="#c98b1d",
        elinewidth=2,
        capsize=4,
        markersize=7,
    )
    ax_t.set_title("Mean time per round (overhead)")
    ax_t.set_xlabel("Time (s)")
    ax_t.set_yticks(y)
    ax_t.set_yticklabels(labels_s)
    if baseline_time is not None:
        ax_t.axvline(baseline_time, color="#6c757d", linestyle="--", linewidth=1.3, alpha=0.8)
    ax_t.set_xlim(max(0.0, t_min - pad), t_max + pad)
    ax_t.grid(axis="x", alpha=0.25, linestyle=":")
    _annotate_h(ax_t, y, times_s, times_std_s, "{:.1f}s")
    fig_t.tight_layout()
    out_t = OUT / "ablation_overview_time.png"
    fig_t.savefig(out_t, bbox_inches="tight")
    plt.close(fig_t)
    print(f"[ok] {out_t}")

    fig_g, ax_g = plt.subplots(figsize=(6.8, 4.2))
    ax_g.bar(x, gas, yerr=gas_std, capsize=5, color="#e76f51")
    ax_g.set_title("Total gas cost")
    ax_g.set_ylabel("Gas (ETH)")
    ax_g.set_xticks(x)
    ax_g.set_xticklabels(labels)
    ax_g.set_ylim(0, max(gas) * 1.25 if max(gas) > 0 else 1)
    _annotate(ax_g, gas, gas_std, "{:.2e}")
    fig_g.tight_layout()
    out_g = OUT / "ablation_overview_gas.png"
    fig_g.savefig(out_g, bbox_inches="tight")
    plt.close(fig_g)
    print(f"[ok] {out_g}")

    fig_a, ax_a = plt.subplots(figsize=(6.8, 4.2))
    ax_a.bar(x, acc, yerr=acc_std, capsize=5, color="#264653")
    ax_a.set_title("Final accuracy per mode")
    ax_a.set_ylabel("Final accuracy")
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(labels)
    ax_a.set_ylim(0, 1.05)
    _annotate(ax_a, acc, acc_std, "{:.4f}")
    fig_a.tight_layout()
    out_a = OUT / "ablation_overview_accuracy.png"
    fig_a.savefig(out_a, bbox_inches="tight")
    plt.close(fig_a)
    print(f"[ok] {out_a}")


def plot_ablation_rounds(ablation_dir):
    """Evolução por round de cada modo, com média ± desvio entre repetições.

    Eixo X = round. Uma curva (média) por modo com banda sombreada ±std para
    accuracy e tempo de treino; o gás cumulativo é ~determinístico. Lê os
    per-rep em ``<dir>/<mode>/rep*/server_metrics.json`` (com fallback para
    o layout antigo ``<dir>/<mode>/server_metrics.json``).
    """
    ablation_dir = Path(ablation_dir)
    modes = ["baseline", "no_ipfs", "full"]
    colors = {"baseline": "#264653", "no_ipfs": "#2a9d8f", "full": "#e76f51"}
    label_map = {
        "baseline": "baseline (Flower puro)",
        "no_ipfs": "no-IPFS (on-chain)",
        "full": "full (on-chain+IPFS)",
    }

    def _rep_files(mode_dir):
        reps = sorted(mode_dir.glob("rep*/server_metrics.json"))
        if not reps:
            single = mode_dir / "server_metrics.json"
            reps = [single] if single.exists() else []
        return reps

    def _round_series(d):
        rounds = [r for r in d.get("rounds", []) if r.get("round", 0) > 0]
        rounds.sort(key=lambda r: r["round"])
        rnums = [r["round"] for r in rounds]
        acc = [r.get("accuracy") for r in rounds]
        tim = [r.get("train_time_round_s") for r in rounds]
        gas = [float(r.get("gas_eth") or 0.0) for r in rounds]
        return rnums, acc, tim, np.cumsum(gas)

    def _stack(list_of_lists):
        L = min(len(x) for x in list_of_lists)
        return np.array(
            [[(v if v is not None else np.nan) for v in x[:L]] for x in list_of_lists],
            dtype=float,
        )

    series = {}
    max_round = 0
    for m in modes:
        files = _rep_files(ablation_dir / m)
        accs, times, cgas, rnums_ref = [], [], [], None
        for f in files:
            d = load(f)
            if d is None:
                continue
            rnums, acc, tim, cg = _round_series(d)
            if not rnums:
                continue
            rnums_ref = rnums
            accs.append(acc)
            times.append(tim)
            cgas.append(cg)
        if rnums_ref is None:
            continue
        max_round = max(max_round, max(rnums_ref))
        acc_arr, time_arr, gas_arr = _stack(accs), _stack(times), _stack(cgas)
        L = acc_arr.shape[1]
        series[m] = {
            "r": rnums_ref[:L],
            "acc_mean": np.nanmean(acc_arr, axis=0),
            "acc_std": np.nanstd(acc_arr, axis=0),
            "time_mean": np.nanmean(time_arr, axis=0),
            "time_std": np.nanstd(time_arr, axis=0),
            "gas_mean": np.nanmean(gas_arr, axis=0),
        }

    if not series:
        print(f"[skip] ablation rounds: nenhum metrics em {ablation_dir}")
        return

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))
    for m in modes:
        if m not in series:
            continue
        s = series[m]
        c, lbl = colors[m], label_map[m]
        ax1.plot(s["r"], s["acc_mean"], marker="o", color=c, label=lbl)
        ax1.fill_between(s["r"], s["acc_mean"] - s["acc_std"],
                         s["acc_mean"] + s["acc_std"], color=c, alpha=0.2)
        ax2.plot(s["r"], s["time_mean"], marker="s", color=c, label=lbl)
        ax2.fill_between(s["r"], s["time_mean"] - s["time_std"],
                         s["time_mean"] + s["time_std"], color=c, alpha=0.2)
        ax3.plot(s["r"], s["gas_mean"], marker="^", color=c, label=lbl)

    xticks = list(range(1, max_round + 1))
    for ax in (ax1, ax2, ax3):
        ax.set_xlabel("Round")
        ax.set_xticks(xticks)

    ax1.set_title("Accuracy per round (mean ± std)")
    ax1.set_ylabel("Accuracy")
    ax1.legend()

    ax2.set_title("Training time per round (mean ± std)")
    ax2.set_ylabel("Time (s)")
    ax2.legend()

    ax3.set_title("Cumulative gas cost")
    ax3.set_ylabel("Gas (ETH)")
    ax3.legend()

    fig.suptitle(f"Ablation Experiment - per-round evolution (rounds={max_round})", fontsize=15)
    fig.tight_layout()
    out = OUT / "ablation_rounds.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")

    # Salva paineis separados (acuracia/tempo/gas cumulativo) por round.
    fig_ra, ax_ra = plt.subplots(figsize=(7.2, 4.2))
    for m in modes:
        if m not in series:
            continue
        s = series[m]
        c, lbl = colors[m], label_map[m]
        ax_ra.plot(s["r"], s["acc_mean"], marker="o", color=c, label=lbl)
        ax_ra.fill_between(s["r"], s["acc_mean"] - s["acc_std"],
                           s["acc_mean"] + s["acc_std"], color=c, alpha=0.2)
    ax_ra.set_title("Accuracy per round (mean ± std)")
    ax_ra.set_xlabel("Round")
    ax_ra.set_ylabel("Accuracy")
    ax_ra.set_xticks(xticks)
    ax_ra.legend()
    fig_ra.tight_layout()
    out_ra = OUT / "ablation_rounds_accuracy.png"
    fig_ra.savefig(out_ra, bbox_inches="tight")
    plt.close(fig_ra)
    print(f"[ok] {out_ra}")

    fig_rt, ax_rt = plt.subplots(figsize=(7.2, 4.2))
    for m in modes:
        if m not in series:
            continue
        s = series[m]
        c, lbl = colors[m], label_map[m]
        ax_rt.plot(s["r"], s["time_mean"], marker="s", color=c, label=lbl)
        ax_rt.fill_between(s["r"], s["time_mean"] - s["time_std"],
                           s["time_mean"] + s["time_std"], color=c, alpha=0.2)
    ax_rt.set_title("Training time per round (mean ± std)")
    ax_rt.set_xlabel("Round")
    ax_rt.set_ylabel("Time (s)")
    ax_rt.set_xticks(xticks)
    ax_rt.legend()
    fig_rt.tight_layout()
    out_rt = OUT / "ablation_rounds_time.png"
    fig_rt.savefig(out_rt, bbox_inches="tight")
    plt.close(fig_rt)
    print(f"[ok] {out_rt}")

    fig_rg, ax_rg = plt.subplots(figsize=(7.2, 4.2))
    for m in modes:
        if m not in series:
            continue
        s = series[m]
        c, lbl = colors[m], label_map[m]
        ax_rg.plot(s["r"], s["gas_mean"], marker="^", color=c, label=lbl)
    ax_rg.set_title("Cumulative gas cost")
    ax_rg.set_xlabel("Round")
    ax_rg.set_ylabel("Gas (ETH)")
    ax_rg.set_xticks(xticks)
    ax_rg.legend()
    fig_rg.tight_layout()
    out_rg = OUT / "ablation_rounds_gas.png"
    fig_rg.savefig(out_rg, bbox_inches="tight")
    plt.close(fig_rg)
    print(f"[ok] {out_rg}")


def plot_marketplace_gas(breakdown_path):
    """Gas breakdown por operacao de marketplace (register/offer/accept/sign/fund).

    Le results/marketplace_gas_breakdown.json (gerado por flower_fl.deploy_job)
    e plota gas_used e gas_eth por operacao, colorindo por papel (requester/trainer).
    """
    data = load(breakdown_path)
    if data is None:
        return
    ops = data.get("operations", [])
    if not ops:
        print("[skip] marketplace gas: sem operacoes")
        return

    labels = [o["operation"] for o in ops]
    gas_used = [o.get("gas_used", 0) for o in ops]
    gas_eth = [o.get("gas_eth", 0.0) for o in ops]
    roles = [o.get("role", "") for o in ops]
    role_color = {"requester": "#2a9d8f", "trainer": "#e76f51"}
    colors = [role_color.get(r, "#577590") for r in roles]

    x = np.arange(len(labels))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    ax1.bar(x, gas_used, color=colors)
    ax1.set_title("Gas used per marketplace operation")
    ax1.set_ylabel("Gas used (units)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=30, ha="right")
    ax1.set_ylim(0, max(gas_used) * 1.15)
    for i, v in enumerate(gas_used):
        ax1.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=8)

    ax2.bar(x, gas_eth, color=colors)
    ax2.set_title("Gas cost per marketplace operation")
    ax2.set_ylabel("Gas (ETH)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=30, ha="right")
    ax2.set_ylim(0, max(gas_eth) * 1.18)
    for i, v in enumerate(gas_eth):
        ax2.text(i, v, f"{v:.2e}", ha="center", va="bottom", fontsize=8)

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=role_color["requester"]),
        plt.Rectangle((0, 0), 1, 1, color=role_color["trainer"]),
    ]
    ax1.legend(handles, ["requester", "trainer"], loc="upper right")

    total_used = data.get("total_gas_used", sum(gas_used))
    total_eth = data.get("total_gas_eth", sum(gas_eth))
    fig.suptitle(
        f"Marketplace Gas Breakdown (total: {total_used:,} gas / {total_eth:.2e} ETH)",
        fontsize=15,
    )
    fig.tight_layout()
    out = OUT / "marketplace_gas_breakdown.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


def plot_matching_scalability(path):
    """Escalabilidade do matchTrainers: gas e latencia vs numero de trainers.

    Le results/matching_load_test.json (gerado por scripts/load_test_matching.ts)
    e contrasta dois regimes do loop de matching:
      - best case (filtro vazio): early-exit apos `canditatesToReturn` matches,
        gas/latencia ~constantes (nao dependem de N).
      - worst case (filtro que nao casa): varredura completa -> O(n) real, o gas
        cresce linearmente com o numero de trainers registrados.
    """
    data = load(path)
    if data is None:
        return
    meas = sorted(data.get("measurements", []), key=lambda m: m["n_trainers"])
    if not meas:
        print("[skip] matching: sem measurements")
        return
    n = [m["n_trainers"] for m in meas]
    gas_best = [int(m["gas_estimated_bestcase"]) for m in meas]
    gas_worst = [int(m["gas_estimated_worstcase"]) for m in meas]
    t_best = [float(m["time_ms_bestcase"]) for m in meas]
    t_worst = [float(m["time_ms_worstcase"]) for m in meas]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    ax1.plot(n, gas_best, marker="o", color="#2a9d8f", label="best case (early-exit)")
    ax1.plot(n, gas_worst, marker="^", color="#e76f51", label="worst case (full scan, O(n))")
    ax1.set_title("matchTrainers gas vs number of trainers")
    ax1.set_xlabel("Number of registered trainers")
    ax1.set_ylabel("Gas estimated")
    ax1.set_xticks(n)
    ax1.legend()
    for xi, v in zip(n, gas_best):
        ax1.annotate(f"{v:,}", (xi, v), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8)
    for xi, v in zip(n, gas_worst):
        ax1.annotate(f"{v:,}", (xi, v), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)

    ax2.plot(n, t_best, marker="o", color="#2a9d8f", label="best case (early-exit)")
    ax2.plot(n, t_worst, marker="^", color="#e76f51", label="worst case (full scan)")
    ax2.axhline(15, color="#264653", linestyle="--", linewidth=1.3, label="15 ms threshold")
    ax2.set_title("matchTrainers latency vs number of trainers")
    ax2.set_xlabel("Number of registered trainers")
    ax2.set_ylabel("Latency (ms)")
    ax2.set_xticks(n)
    ax2.set_ylim(0, max(max(t_worst), 15) * 1.2)
    ax2.legend()

    fig.suptitle("Marketplace Matching Scalability (best-case O(1) vs worst-case O(n))", fontsize=15)
    fig.tight_layout()
    out = OUT / "matching_scalability.png"
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
    ax.set_title("Accuracy curves per round")
    ax.set_xlabel("Round")
    ax.set_ylabel("Accuracy")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    out = OUT / "accuracy_curves.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")


if __name__ == "__main__":
    plot_scaling(RESULTS / "scaling_mnist_rep3" / "scaling_summary.json")
    # Novos summaries full-mode com detector real.
    plot_security(
        RESULTS / "security_full_scaling" / "security_summary.json",
        attack_label="scaling",
        out_name="security_overview_scaling.png",
    )
    plot_security(
        RESULTS / "security_full_noise" / "security_summary.json",
        attack_label="noise",
        out_name="security_overview_noise.png",
    )
    plot_security(
        RESULTS / "security_full_labelflip" / "security_summary.json",
        attack_label="labelflip",
        out_name="security_overview_labelflip.png",
    )
    plot_security_detector_comparison(
        RESULTS / "security_full_scaling" / "security_summary.json",
        RESULTS / "security_full_noise" / "security_summary.json",
        RESULTS / "security_full_labelflip" / "security_summary.json",
    )
    plot_ksens(RESULTS / "sensitivity_k" / "ksens_summary.json")
    # Mantem compatibilidade com o summary baseline legado.
    plot_security(RESULTS / "security_test2" / "security_summary.json")
    plot_ablation(RESULTS / "ablation_full" / "ablation_summary.json")
    plot_ablation_rounds(RESULTS / "ablation_full")
    plot_marketplace_gas(RESULTS / "marketplace_gas_breakdown.json")
    plot_matching_scalability(RESULTS / "matching_load_test.json")
    plot_accuracy_curves()
    print(f"\nFiguras geradas em: {OUT}/")
