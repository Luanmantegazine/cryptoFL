# Rodando o CryptoFL na GPU (Google Colab)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Luanmantegazine/cryptoFL/blob/claude/loving-hypatia-f54mj0/colab_gpu.ipynb)

O `scaling_experiment.py` detecta CUDA automaticamente (`flower_fl/client.py` →
`torch.device("cuda" if torch.cuda.is_available() else "cpu")`). Em GPU, o
CIFAR-10/ResNet-18 sai de **~30 min/round (CPU) para segundos**, e as quedas que
travavam o sweep em CPU (OOM / *gRPC ping timeout* em rounds longas) desaparecem,
porque cada round termina rápido e a CPU fica livre para o servidor.

> Não precisa de multi-GPU: o servidor + os N clientes dividem **uma** GPU.
> ResNet-18 é pequeno, então até N=10 cabe folgado em uma T4 (16 GB).

## Passo a passo

### 1. Abrir o notebook no Colab
Clique no botão **Open In Colab** acima (abre `colab_gpu.ipynb` direto do GitHub),
ou vá em <https://colab.research.google.com> → *File → Open notebook → GitHub* →
cole `Luanmantegazine/cryptoFL` e escolha o branch `claude/loving-hypatia-f54mj0`.

### 2. Ativar a GPU
Menu **Runtime → Change runtime type → Hardware accelerator → GPU (T4)** → *Save*.

### 3. Rodar
**Runtime → Run all** (ou rode célula por célula). A ordem é:

| Célula | O que faz | Tempo aprox. (T4) |
|---|---|---|
| 0 | Confirma a GPU (`nvidia-smi`) | instantâneo |
| 1 | Clona o repo + `pip install flwr==1.7.0` | ~1 min |
| 2 | Teste rápido (N=2, 1 round, MNIST) | ~1 min |
| 3 | (opcional) Sweep MNIST completo | ~15–25 min |
| 4 | **Sweep CIFAR-10 / ResNet-18 completo** | ~30–90 min |
| 5 | Tabela SUMMARY + figuras inline | instantâneo |
| 6 | Salva resultados (zip/download ou Drive) | ~1 min |

> Só quer o **ponto único** de CIFAR (mais rápido)? Na célula 4 troque
> `--clients-list 2,4,6,8,10 ... --repetitions 3` por
> `--clients-list 2 --repetitions 1` (~5–10 min).

### 4. Salvar os resultados
A VM do Colab é **efêmera** — tudo é apagado quando a sessão encerra. A célula 6
baixa um `resultados.zip` (pasta `results/` + `logs/`). Para algo mais durável,
use a Opção B (montar o Google Drive e copiar `results/` para lá).

## Comandos equivalentes (se preferir rodar via terminal/VM com GPU)

```bash
git clone -b claude/loving-hypatia-f54mj0 https://github.com/Luanmantegazine/cryptoFL.git
cd cryptoFL
pip install "flwr==1.7.0"                    # NÃO force numpy<2 no Colab (torchvision é numpy 2.x)
pip install -U "protobuf>=5.26,<6"           # grpcio do Colab exige protobuf 5.x (ver abaixo)

# CIFAR completo (agora viável na GPU). --min-fraction 0.8 = se um cliente cair,
# a run segue com os demais em vez de travar esperando quórum.
KMP_DUPLICATE_LIB_OK=TRUE python scaling_experiment.py \
    --clients-list 2,4,6,8,10 --rounds 3 \
    --aggregators fedavg,fedprox --repetitions 3 \
    --dataset cifar10 --model resnet18 --alpha 0.5 --min-fraction 0.8 \
    --output-dir results/scaling_cifar 2>&1 | tee logs/scaling_cifar.log
```

## Se o sweep "roda em loop" e não plota

Quase sempre é **branch ou ambiente errado**, não o experimento:

- **Branch errado:** o clone PRECISA ser `-b claude/loving-hypatia-f54mj0`. O `main`
  não tem o watchdog nem o `round_timeout` finito, então um cliente que não conecta
  a tempo faz o servidor esperar quórum **para sempre** → a célula nunca termina e o
  `scaling_summary.json`/PNGs (escritos só no fim) nunca aparecem. Confirme com
  `!git log --oneline -1` logo após o clone.
- **`protobuf` tem que ser 5.x no Colab:** o grpcio do Colab (>=1.71) exige
  `protobuf>=5.26`. O flwr fixa `<5` e o pip rebaixa pra 4.x ao instalar — aí os
  clientes **morrem no startup** (`[WARN] clients died right after spawn`). Conserto:
  `pip install -U "protobuf>=5.26,<6"`. O aviso `flwr requires protobuf<5` é inofensivo
  (o pipeline roda com 5.x).
- **NÃO fixe `numpy<2` no Colab:** o torch/torchvision do Colab são compilados para
  numpy 2.x; rebaixar dá `ValueError: numpy.dtype size changed ... Expected 96 ... got 88`
  ao `import torchvision`. Deixe o numpy 2.x do Colab (o flwr roda com ele). Se já
  rebaixou: `pip install -U "numpy>=2.0"` e **Runtime → Restart session**.
- **Recomeçar limpo:** *Runtime → Disconnect and delete runtime*, reabra pelo botão
  *Open in Colab* (pega a versão correta do notebook) e rode tudo de novo.

## Observações

- **Verificar que está na GPU durante o run:** rode `!nvidia-smi` em outra
  célula — devem aparecer processos `python` ocupando a placa.
- **Conflito de versões:** se o `flwr==1.7.0` brigar com o `numpy`/`torch` do
  Colab, rode `!pip install -q "flwr==1.7.0" "numpy<2.0"` e
  **Runtime → Restart runtime** antes de seguir.
- **Free tier do Colab** desconecta após ~90 min ocioso e tem sessão de ~12 h —
  o sweep CIFAR cabe, mas mantenha a aba ativa. Para sweeps longos, uma VM paga
  com GPU (RunPod, vast.ai, Lambda, GCP) é mais segura.
- Os envs `KMP_DUPLICATE_LIB_OK` / `OMP_NUM_THREADS=1` são para CPU/macOS;
  no Linux/GPU são inofensivos (mantidos só por paridade com o comando local).
