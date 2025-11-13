import torch
from torchvision import datasets, transforms


def load_mnist(node_id, num_nodes=3):
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
