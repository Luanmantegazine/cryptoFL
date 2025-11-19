import flwr as fl
import os
import torch
import torch.nn as nn


from .models import MNISTNet
from .datasets import load_mnist
from .ipfs import ipfs_get_numpy, ipfs_add_numpy
from .onchain_job import job_send_update

JOB_ADDR = os.getenv("JOB_ADDR")
assert JOB_ADDR, "JOB_ADDR não encontrado no .env"


class MNISTClient(fl.client.NumPyClient):
    def __init__(self, node_id, num_nodes):
        self.node_id = node_id
        self.model = MNISTNet()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        print(f"[Cliente {node_id}] Carregando dados...")

        # ✅ CORREÇÃO: Desempacota os DOIS loaders retornados
        self.trainloader, self.testloader = load_mnist(node_id, num_nodes)

        print(f"[Cliente {node_id}] Treino: {len(self.trainloader.dataset)} amostras")
        print(f"[Cliente {node_id}] Teste:  {len(self.testloader.dataset)} amostras")

    def get_parameters(self, config):
        if "cid_global" in config:
            cid = config["cid_global"]
            print(f"[Cliente {self.node_id}] Baixando modelo global: {cid}")
            params = ipfs_get_numpy(cid)
            self.set_parameters(params)
        else:
            print(f"[Cliente {self.node_id}] Enviando parâmetros iniciais.")
        return [val.cpu().numpy() for _, val in self.model.state_dict().items()]

    def set_parameters(self, parameters):
        params_dict = zip(self.model.state_dict().keys(), parameters)
        state_dict = {k: torch.tensor(v) for k, v in params_dict}
        self.model.load_state_dict(state_dict, strict=True)

    def fit(self, parameters, config):
        self.set_parameters(parameters)
        optimizer = torch.optim.Adam(self.model.parameters())
        criterion = nn.NLLLoss()
        self.model.train()
        self.model.to(self.device)


        server_round = config.get("server_round", "?")
        print(f"[Cliente {self.node_id}] Rodada {server_round}: Iniciando treino...")

        epochs = int(config.get("epochs", 1))
        for _ in range(epochs):
            for images, labels in self.trainloader:
                images, labels = images.to(self.device), labels.to(self.device)
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

        # Salvar e enviar
        updated_params = [val.cpu().numpy() for _, val in self.model.state_dict().items()]
        cid_up = ipfs_add_numpy(updated_params, f"mnist_update_c{self.node_id}_r{server_round}.npz")

        print(f"[Cliente {self.node_id}] Publicando update: {cid_up}")
        try:
            r = job_send_update(JOB_ADDR, cid_up)
            print(f"[JOB] Tx enviada: {r['hash']}")
        except Exception as e:
            print(f"[ERRO] Falha na blockchain: {e}")

        return updated_params, len(self.trainloader.dataset), {"cid": cid_up}

    def evaluate(self, parameters, config):
        self.set_parameters(parameters)
        self.model.eval()
        self.model.to(self.device)

        loss, correct = 0, 0
        criterion = nn.NLLLoss()

        # Usa o self.testloader agora disponível
        with torch.no_grad():
            for images, labels in self.testloader:
                images, labels = images.to(self.device), labels.to(self.device)
                outputs = self.model(images)
                loss += criterion(outputs, labels).item()
                correct += (outputs.argmax(1) == labels).sum().item()

        accuracy = correct / len(self.testloader.dataset)
        print(f"[Cliente {self.node_id}] Evaluate: Acc={accuracy:.4f}")

        return float(loss), len(self.testloader.dataset), {"accuracy": float(accuracy)}


if __name__ == "__main__":
    NODE_ID = int(os.getenv("NODE_ID", "0"))
    NUM_NODES = int(os.getenv("NUM_NODES", "10"))

    print(f"\n{'=' * 70}")
    print(f" CLIENTE {NODE_ID}/{NUM_NODES - 1}")
    print(f"{'=' * 70}\n")

    client = MNISTClient(node_id=NODE_ID, num_nodes=NUM_NODES).to_client()
    fl.client.start_client(server_address="0.0.0.0:8080", client=client)