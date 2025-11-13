import os

os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import multiprocessing

multiprocessing.set_start_method('spawn', force=True)

import sys
import time
from datetime import datetime

import flwr as fl
import torch
import torch.nn.functional as F

# Imports locais
from models import MNISTNet
from datasets import load_mnist
from onchain_job import job_send_update
from ipfs import ipfs_add_numpy

# Configurações
JOB_ADDR = os.getenv("JOB_ADDR")
NODE_ID = int(os.getenv("NODE_ID", "0"))
NUM_NODES = int(os.getenv("NUM_NODES", "3"))
EPOCHS_PER_ROUND = int(os.getenv("EPOCHS_PER_ROUND", "1"))
LEARNING_RATE = float(os.getenv("LEARNING_RATE", "0.001"))

if not JOB_ADDR:
    raise RuntimeError(
        " ERRO: Configure JOB_ADDR no .env\n"
        "Exemplo: JOB_ADDR=0xeEBe00Ac0756308ac4AaBfD76c05c4F3088B8883"
    )


class MNISTClient(fl.client.NumPyClient):
    """Cliente Flower para treinamento MNIST"""

    def __init__(self, node_id, num_nodes):
        self.node_id = node_id
        self.num_nodes = num_nodes

        print(f"\n{'=' * 60}")
        print(f" CLIENTE {node_id} (Node {node_id + 1}/{num_nodes})")
        print(f"{'=' * 60}")

        # Configurar dispositivo
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"⚙  Dispositivo: {self.device}")

        # Criar modelo
        print(f" Inicializando MNISTNet...")
        self.model = MNISTNet()
        self.model.to(self.device)

        # Carregar dataset
        print(f" Carregando dataset MNIST...")
        self.trainloader, self.testloader = load_mnist(node_id, num_nodes)

        print(f" Cliente inicializado!")
        print(f"   Amostras treino: {len(self.trainloader.dataset)}")
        print(f"   Amostras teste: {len(self.testloader.dataset)}")
        print(f"   Batches: {len(self.trainloader)}")
        print(f"{'=' * 60}\n")

    def get_parameters(self, config):
        """Retorna parâmetros atuais do modelo"""
        print(f"[Cliente {self.node_id}] 📤 Servidor solicitou parâmetros")
        params = [val.cpu().numpy() for _, val in self.model.state_dict().items()]
        print(f"[Cliente {self.node_id}]    Enviando {len(params)} camadas")
        return params

    def set_parameters(self, parameters):
        """Atualiza modelo com parâmetros recebidos"""
        params_dict = zip(self.model.state_dict().keys(), parameters)
        state_dict = {k: torch.tensor(v) for k, v in params_dict}
        self.model.load_state_dict(state_dict, strict=True)

    def fit(self, parameters, config):
        """Treina modelo localmente"""
        server_round = config.get("server_round", "?")
        cid_global = config.get("cid_global", "N/A")

        print(f"\n{'=' * 60}")
        print(f" ROUND {server_round} - Cliente {self.node_id}")
        print(f"{'=' * 60}")
        print(f" Início: {datetime.now().strftime('%H:%M:%S')}")
        print(f" CID modelo global: {cid_global}")

        # Atualizar modelo com parâmetros globais
        print(f"[1/5] Carregando parâmetros globais...")
        self.set_parameters(parameters)

        # Treinar localmente
        print(f"[2/5] Treinando modelo ({EPOCHS_PER_ROUND} época(s))...")
        start_time = time.time()

        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=LEARNING_RATE)

        epoch_losses = []
        for epoch in range(EPOCHS_PER_ROUND):
            batch_losses = []

            for batch_idx, (images, labels) in enumerate(self.trainloader):
                images, labels = images.to(self.device), labels.to(self.device)

                # Forward + Backward
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = F.cross_entropy(outputs, labels)
                loss.backward()
                optimizer.step()

                batch_losses.append(loss.item())

                # Log a cada 20% do progresso
                if batch_idx % max(1, len(self.trainloader) // 5) == 0:
                    progress = (batch_idx + 1) / len(self.trainloader) * 100
                    print(f"      Época {epoch + 1}/{EPOCHS_PER_ROUND} | "
                          f"Batch {batch_idx}/{len(self.trainloader)} ({progress:.0f}%) | "
                          f"Loss: {loss.item():.4f}")

            avg_loss = sum(batch_losses) / len(batch_losses)
            epoch_losses.append(avg_loss)
            print(f"       Época {epoch + 1} concluída | Loss médio: {avg_loss:.4f}")

        train_time = time.time() - start_time
        print(f"        Tempo de treino: {train_time:.2f}s")

        # Obter parâmetros atualizados
        print(f"[3/5] Extraindo parâmetros atualizados...")
        updated_params = self.get_parameters({})
        num_samples = len(self.trainloader.dataset)

        # Upload para IPFS
        print(f"[4/5] Salvando update no IPFS...")
        try:
            cid_update = ipfs_add_numpy(
                updated_params,
                f"client{self.node_id}_round{server_round}.npz"
            )
            print(f"      ✓ CID: {cid_update}")
        except Exception as e:
            print(f"      ✗ ERRO IPFS: {e}")
            cid_update = "ERROR"

        # Registrar on-chain
        print(f"[5/5] Registrando update on-chain...")
        try:
            result = job_send_update(JOB_ADDR, cid_update)
            print(f"      ✓ Tx: {result['hash']}")
            print(f"      ✓ Gas: {result['gasETH']:.8f} ETH")
        except Exception as e:
            print(f"      ✗ ERRO Blockchain: {e}")

        # Resumo
        print(f"\n Round {server_round} concluído!")
        print(f"    Loss final: {epoch_losses[-1]:.4f}")
        print(f"    Amostras: {num_samples}")
        print(f"     Tempo: {train_time:.2f}s")
        print(f"{'=' * 60}\n")

        return updated_params, num_samples, {
            "cid": cid_update,
            "loss": epoch_losses[-1],
            "train_time": train_time,
        }

    def evaluate(self, parameters, config):
        """Avalia modelo no dataset de teste"""
        print(f"\n[Cliente {self.node_id}]  Avaliando modelo...")

        self.set_parameters(parameters)
        self.model.eval()

        total_loss = 0.0
        correct = 0
        total = 0

        with torch.no_grad():
            for images, labels in self.testloader:
                images, labels = images.to(self.device), labels.to(self.device)

                outputs = self.model(images)
                loss = F.cross_entropy(outputs, labels)
                total_loss += loss.item()

                predicted = outputs.argmax(dim=1)
                correct += (predicted == labels).sum().item()
                total += labels.size(0)

        accuracy = correct / total
        avg_loss = total_loss / len(self.testloader)

        print(f"[Cliente {self.node_id}]    Acurácia: {accuracy:.4f} ({correct}/{total})")
        print(f"[Cliente {self.node_id}]    Loss: {avg_loss:.4f}")

        return avg_loss, len(self.testloader.dataset), {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
        }


def main():
    """Função principal do cliente"""
    print("\n" + "=" * 70)
    print(" FLOWER FEDERATED LEARNING CLIENT")
    print("=" * 70)
    print(f" Node ID: {NODE_ID}")
    print(f" Total Nodes: {NUM_NODES}")
    print(f" Job Address: {JOB_ADDR[:20]}...")
    print(f" Épocas por round: {EPOCHS_PER_ROUND}")
    print(f" Learning Rate: {LEARNING_RATE}")
    print("=" * 70)

    try:
        # Criar cliente
        client = MNISTClient(NODE_ID, NUM_NODES)

        # Conectar ao servidor
        print(f"\n🔌 Conectando ao servidor (0.0.0.0:8080)...\n")

        fl.client.start_client(
            server_address="0.0.0.0:8080",
            client=client.to_client(),
            grpc_max_message_length=536870912,  # 512MB
        )

        print(f"\n Cliente {NODE_ID} finalizado com sucesso!\n")

    except KeyboardInterrupt:
        print(f"\n\n Cliente {NODE_ID} interrompido pelo usuário")
    except Exception as e:
        print(f"\n ERRO FATAL no Cliente {NODE_ID}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()