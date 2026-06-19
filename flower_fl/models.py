import torch.nn as nn
import torch
import torch.nn.functional as F
from torchvision import models as tvm


class MNISTNet(nn.Module):
    def __init__(self):
        super(MNISTNet, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.dropout1 = nn.Dropout(0.25)
        self.dropout2 = nn.Dropout(0.5)
        self.fc1 = nn.Linear(9216, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = self.conv1(x)
        x = F.relu(x)
        x = self.conv2(x)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)
        x = self.dropout1(x)
        x = torch.flatten(x, 1)
        x = self.fc1(x)
        x = F.relu(x)
        x = self.dropout2(x)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


class ResNet18Flower(nn.Module):
    """ResNet-18 adaptada para imagens pequenas (32×32, ex.: CIFAR-10).

    Substitui a conv1 7×7/stride 2 da ResNet original (projetada para
    ImageNet 224×224) por uma conv 3×3/stride 1 e remove o maxpool inicial,
    preservando resolução espacial suficiente para imagens 32×32. A camada
    final `fc` é trocada por uma `Linear(512, num_classes)`.

    `in_channels` permite usar com MNIST (1 canal); default 3 (CIFAR-10).
    """

    def __init__(self, num_classes: int = 10, in_channels: int = 3):
        super().__init__()
        backbone = tvm.resnet18(weights=None)

        # Adapta conv1 para imagens pequenas (e número de canais variável).
        backbone.conv1 = nn.Conv2d(
            in_channels, 64,
            kernel_size=3, stride=1, padding=1, bias=False,
        )
        # Remove maxpool inicial (preserva resolução em 32×32).
        backbone.maxpool = nn.Identity()
        # Cabeça de classificação.
        backbone.fc = nn.Linear(512, num_classes)

        self.model = backbone

    def forward(self, x):
        x = self.model(x)
        return F.log_softmax(x, dim=1)


def get_model(name: str, **kwargs) -> nn.Module:
    """Dispatcher de modelo por nome ('mnistnet' | 'resnet18')."""
    key = (name or "").lower()
    if key == "mnistnet":
        return MNISTNet()
    if key == "resnet18":
        return ResNet18Flower(**kwargs)
    raise ValueError(f"Modelo '{name}' não suportado.")
