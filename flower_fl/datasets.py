import os
import torch
import numpy as np
from torchvision import datasets, transforms


# SEED de módulo (usado por load_cifar10 para o particionamento Dirichlet).
SEED = int(os.getenv("SEED", "42"))


def load_mnist(node_id, num_nodes=3):
    # Seed opcional para reprodutibilidade entre repetições do multi_run.
    seed_env = os.getenv("SEED")
    if seed_env is not None:
        try:
            seed = int(seed_env)
            torch.manual_seed(seed)
            np.random.seed(seed)
        except ValueError:
            pass

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Download dataset
    train_dataset = datasets.MNIST(
        './data', train=True, download=True, transform=transform
    )
    test_dataset = datasets.MNIST(
        './data', train=False, download=True, transform=transform
    )

    total_train = len(train_dataset)  # 60000
    partition_size = total_train // num_nodes

    start_idx = node_id * partition_size
    end_idx = start_idx + partition_size

    # Último node pega o resto
    if node_id == num_nodes - 1:
        end_idx = total_train

    # Criar subset
    train_subset = torch.utils.data.Subset(
        train_dataset,
        list(range(start_idx, end_idx))
    )

    print(f"[Dataset] Node {node_id}: índices {start_idx}-{end_idx} ({len(train_subset)} amostras)")

    # DataLoaders SEM workers (evita fork)
    trainloader = torch.utils.data.DataLoader(
        train_subset,
        batch_size=32,
        shuffle=True,
        num_workers=0,
        pin_memory=False
    )

    testloader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=32,
        shuffle=False,
        num_workers=0,
        pin_memory=False
    )

    return trainloader, testloader


def load_cifar10(node_id: int, num_nodes: int, alpha: float = 0.5):
    """Carrega CIFAR-10 com particionamento não-IID via Dirichlet(α).

    Para cada classe c em {0..9}, amostra proporções
    ``p_c ~ Dirichlet([alpha] * num_nodes)`` e distribui as amostras dessa
    classe entre os nós conforme essas proporções. O nó `node_id` recebe
    apenas a sua fatia.

    - α pequeno (ex.: 0.1) ⇒ partições altamente não-IID (cada nó concentra
      poucas classes).
    - α grande (ex.: 100.0) ⇒ partições aproximadamente IID.
    """
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(
            (0.4914, 0.4822, 0.4465),
            (0.2470, 0.2435, 0.2616),
        ),
    ])

    train_dataset = datasets.CIFAR10(
        './data', train=True, download=True, transform=transform
    )
    test_dataset = datasets.CIFAR10(
        './data', train=False, download=True, transform=transform
    )

    targets = np.array(train_dataset.targets)
    num_classes = 10

    # Para cada classe, dividir índices entre os nós segundo Dirichlet(α).
    node_indices = [[] for _ in range(num_nodes)]
    for c in range(num_classes):
        idx_c = np.where(targets == c)[0]
        np.random.shuffle(idx_c)

        proportions = np.random.dirichlet([alpha] * num_nodes)
        # Cumulativo → pontos de corte
        cuts = (np.cumsum(proportions) * len(idx_c)).astype(int)[:-1]
        splits = np.split(idx_c, cuts)
        for n, split in enumerate(splits):
            node_indices[n].extend(split.tolist())

    my_indices = node_indices[node_id]
    train_subset = torch.utils.data.Subset(train_dataset, my_indices)

    print(f"[Dataset] Node {node_id}: {len(train_subset)} amostras CIFAR-10 (α={alpha})")

    trainloader = torch.utils.data.DataLoader(
        train_subset,
        batch_size=32,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
    )
    testloader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=32,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )
    return trainloader, testloader


def load_dataset(name: str, node_id: int, num_nodes: int, **kwargs):
    """Dispatcher: seleciona o loader pelo nome ('mnist' | 'cifar10')."""
    key = (name or "").lower()
    if key == "mnist":
        return load_mnist(node_id, num_nodes)
    if key == "cifar10":
        return load_cifar10(node_id, num_nodes, alpha=kwargs.get("alpha", 0.5))
    raise ValueError(f"Dataset '{name}' não suportado. Use 'mnist' ou 'cifar10'.")
