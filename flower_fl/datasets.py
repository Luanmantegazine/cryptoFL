from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms


def load_mnist(node_id: int, num_nodes: int):

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Baixa o dataset de treino
    try:
        train_data = datasets.MNIST(
            root="./data",
            train=True,
            download=True,
            transform=transform
        )
    except Exception as e:
        print(f"Falha ao baixar MNIST. Verifique a conexão. Erro: {e}")
        # Tenta carregar localmente se já baixado
        train_data = datasets.MNIST(
            root="./data",
            train=True,
            download=False,
            transform=transform
        )

    # Particiona o dataset
    total_size = len(train_data)
    indices = list(range(total_size))
    # Divide os índices em 'num_nodes' partes
    partition_size = total_size // num_nodes
    start = node_id * partition_size
    # Garante que o último cliente pegue o restante
    if node_id == num_nodes - 1:
        end = total_size
    else:
        end = (node_id + 1) * partition_size

    client_indices = indices[start:end]
    client_dataset = Subset(train_data, client_indices)

    return DataLoader(client_dataset, batch_size=32, shuffle=True)