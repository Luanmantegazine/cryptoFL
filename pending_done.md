# Pending experiments — Done

Todos os três experimentos pendentes foram executados **em ordem** e **passaram**.
Ambiente: macOS, Python `/opt/miniconda3/bin/python` (3.10.13), Flower 1.20.0,
Hardhat 3.9.0 (node localhost chainId 31337), IPFS Kubo 0.42.0.

---

## Experimento 1 — multi_run com variância

**Status: ✅ PASSOU**

Comando (com workaround OMP, ver "Problemas conhecidos"):

```bash
KMP_DUPLICATE_LIB_OK=TRUE python multi_run.py
```

Verificação:

```bash
python -c "
import json
d = json.load(open('results/multi_run/summary.json'))
print('N  | mean_acc | std_acc | mean_time_s | std_time_s')
for n, v in sorted(d['results'].items(), key=lambda x: int(x[0])):
    print(f'{n:<3}| {v[\"mean_accuracy\"]:.4f}   | {v[\"std_accuracy\"]:.4f}  | {v[\"mean_time_s\"]:.1f}        | {v[\"std_time_s\"]:.1f}')
assert all(v['std_accuracy'] > 0 for v in d['results'].values()), 'std must be > 0 with 3 reps'
print('OK')
"
```

Saída-chave:

```
N  | mean_acc | std_acc | mean_time_s | std_time_s
3  | 0.9738   | 0.0005  | 171.0        | 26.3
5  | 0.9676   | 0.0012  | 327.6        | 280.3
OK
```

- `std_accuracy > 0` para ambos os N (3 repetições produzem variância real). Assert passou.

---

## Experimento 2 — matching load test

**Status: ✅ PASSOU**

Comando (ver "Problemas conhecidos" sobre `LOAD_TEST_N`):

```bash
LOAD_TEST_N=100 npx hardhat run scripts/load_test_matching.ts --network localhost
```

Verificação:

```bash
python -c "
import json
d = json.load(open('results/matching_load_test.json'))
print('N trainers | time_ms | gas_estimated')
for m in d['measurements']:
    print(f\"{m['n_trainers']:<12}| {m['time_ms']:<8}| {m['gas_estimated']}\")
assert len(d['measurements']) >= 2, 'expected at least 2 measurements'
print('OK')
"
```

Saída-chave:

```
N trainers | time_ms | gas_estimated
10          | 13.969  | 145481
50          | 6.453   | 145481
100         | 14.291  | 145481
OK
```

**Observação importante (achado, não bug):** o `gas_estimated` é **constante (145481)** e
`matched=5` em todos os N. Isso indica que `matchTrainers` é **O(1) em N** — ele retorna
um número fixo de candidatos (`canditatesToReturn = 5`), independentemente de quantos
trainers estão registrados. O `time_ms` é ruidoso (é uma chamada view, muito rápida; a
variação 6–14 ms é jitter de medição, não crescimento com N). Ou seja, **o custo de
matching não cresce linearmente com o número de trainers**, ao contrário do que o guia
sugeria esperar. Vale registrar isso no paper como propriedade de escalabilidade.

---

## Experimento 3 — CIFAR-10 + ResNet-18 baseline

**Status: ✅ PASSOU**

Comando (orquestrado: servidor na 8081 + 2 clientes, modo baseline):

```bash
KMP_DUPLICATE_LIB_OK=TRUE ROUNDS=2 MIN_CLIENTS=2 DATASET=cifar10 MODEL=resnet18 \
BASELINE_METRICS_FILE=results/cifar10_test.json \
  python -u -m flower_fl.baseline_runner          # servidor
# após a porta 8081 escutar, 2 clientes:
KMP_DUPLICATE_LIB_OK=TRUE BASELINE_AS_CLIENT=1 NODE_ID=0 NUM_NODES=2 \
  DATASET=cifar10 MODEL=resnet18 python -u -m flower_fl.baseline_runner
KMP_DUPLICATE_LIB_OK=TRUE BASELINE_AS_CLIENT=1 NODE_ID=1 NUM_NODES=2 \
  DATASET=cifar10 MODEL=resnet18 python -u -m flower_fl.baseline_runner
```

Verificação:

```bash
python -c "
import json
d = json.load(open('results/cifar10_test.json'))
print(f'Accuracy: {d[\"final_accuracy\"]:.4f}')
for r in d['rounds']:
    if r['round']==0: continue
    print(f'  Round {r[\"round\"]}: {r.get(\"accuracy\",0):.4f}')
assert d['final_accuracy'] > 0.1
assert d['total_gas_eth'] == 0.0
print('OK')
"
```

Saída-chave:

```
Accuracy: 0.6925
  Round 1: 0.5693
  Round 2: 0.6925
OK
```

- Acurácia final **69.25%** (muito acima do baseline aleatório de 10%).
- `total_gas_eth == 0.0` (modo baseline, sem on-chain). Asserts passaram.
- Tempo: Round 1 ≈ 1903s, Round 2 ≈ 2215s, total ≈ 4128s (~69 min) em CPU.

---

## Problemas conhecidos / workarounds aplicados

1. **OMP Error #15 (libomp carregado em duplicidade).** Quando um driver Python importa
   `torch` e também lança subprocessos que importam `torch`, o runtime entra em deadlock
   (estado UE) no init do OpenMP. **Solução:** exportar `KMP_DUPLICATE_LIB_OK=TRUE` antes
   de rodar (`multi_run.py` e o baseline CIFAR). É apenas variável de ambiente — nenhuma
   alteração de código foi necessária.

2. **Hardhat 3 não repassa argumentos posicionais.** `npx hardhat run script.ts --network
   localhost 100` falha com `HHE506` ("100 não consumido"); sem o argumento, `process.argv[2]`
   vira `"run"` (erro "Argumento N inválido: 'run'"). **Solução (alteração de código em
   `scripts/load_test_matching.ts`):** o script agora lê a variável de ambiente
   `LOAD_TEST_N` (com fallback para `argv[2]` e default 100):

   ```ts
   const N_RAW = process.env.LOAD_TEST_N ?? process.argv[2] ?? "100";
   const N_MAX = parseInt(N_RAW, 10);
   ```

   Rode com `LOAD_TEST_N=100 npx hardhat run scripts/load_test_matching.ts --network localhost`.

3. **Mirror oficial do CIFAR-10 (toronto) fora do ar.** `https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz`
   travava em 0 B/s (ETA ~2.6h), enquanto a conectividade geral estava OK (Google a ~260 kB/s).
   **Solução:** baixei do mirror `https://cs231n.stanford.edu/cifar-10-python.tar.gz`
   (HTTP 200, 170.497.704 bytes, ~8.7 MB/s) e extraí manualmente em `./data/cifar-10-batches-py/`.
   O MD5 do `.tar.gz` saiu diferente (`3aa16ff4...` vs `c58f3010...` esperado pelo torchvision) —
   isso é só recompressão gzip com header diferente; o conteúdo interno é idêntico. O
   `torchvision._check_integrity` valida os **batches já extraídos** (não o tar.gz), então
   o `download=True` aceita os arquivos e pula o re-download. Confirmado: `train ok: 50000`,
   `test ok: 10000`.

4. **Conflito de porta 8080** (resolvido em fase anterior): o gateway IPFS usava 8080,
   mesma porta do servidor Flower. Movido para 8088 via
   `ipfs config Addresses.Gateway /ip4/127.0.0.1/tcp/8088` e atualizado `IPFS_GATEWAYS` no `.env`.

---

## Arquivos de resultado gerados

- `results/multi_run/summary.json` — Exp 1
- `results/matching_load_test.json` — Exp 2
- `results/cifar10_test.json` — Exp 3

Tudo pronto para iniciar a escrita do paper.
