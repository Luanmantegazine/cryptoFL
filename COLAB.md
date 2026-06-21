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
pip install "flwr==1.7.0" "numpy<2.0"   # torch/torchvision com CUDA já no ambiente

# CIFAR completo (agora viável na GPU)
KMP_DUPLICATE_LIB_OK=TRUE python scaling_experiment.py \
    --clients-list 2,4,6,8,10 --rounds 3 \
    --aggregators fedavg,fedprox --repetitions 3 \
    --dataset cifar10 --model resnet18 --alpha 0.5 \
    --output-dir results/scaling_cifar 2>&1 | tee logs/scaling_cifar.log
```

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
