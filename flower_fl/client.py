import flwr as fl
import os
import torch
import torch.nn as nn
import argparse
from models import MNISTNet
from datasets import load_mnist
from ipfs import ipfs_get_numpy, ipfs_add_numpy
from onchain_job import job_send_update

JOB_ADDR = os.getenv("JOB_ADDR")
assert JOB_ADDR, "JOB_ADDR não encontrado no .env. Execute o deploy-job.py primeiro."


class MNISTClient(fl.client.NumPyClient):
    def __init__(self, node_id, num_nodes):
        self.node_id = node_id
        self.model = MNISTNet()
        self.trainloader = load_mnist(node_id, num_nodes)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[Cliente {node_id}] Dispositivo: {self.device}, Amostras: {len(self.trainloader.dataset)}")

    def get_parameters(self, config):
        if "cid_global" in config:
            cid = config["cid_global"]
            print(f"[Cliente {self.node_id}] Baixando modelo global do IPFS: {cid}")
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

        print(f"[Cliente {self.node_id}] Iniciando fit (treino)...")
        for epoch in range(config.get("epochs", 1)):
            for images, labels in self.trainloader:
                images, labels = images.to(self.device), labels.to(self.device)
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
        print(f"[Cliente {self.node_id}] Fit concluído.")

        # Salvar no IPFS
        params = self.get_parameters({})
        cid_up = ipfs_add_numpy(params, f"mnist_update_client_{self.node_id}.npz")

        # Registrar on-chain
        print(f"[Cliente {self.node_id}] Publicando update local no IPFS: {cid_up}")
        r = job_send_update(JOB_ADDR, cid_up)
        print(f"[JOB {JOB_ADDR}] SendUpdate tx={r['hash']} gas={r['gasETH']:.8f} ETH")

        return params, len(self.trainloader.dataset), {"cid": cid_up}

    def evaluate(self, parameters, config):
        self.set_parameters(parameters)
        self.model.eval()
        self.model.to(self.device)

        loss, correct = 0, 0
        criterion = nn.NLLLoss()

        with torch.no_grad():
            for images, labels in self.trainloader:
                images, labels = images.to(self.device), labels.to(self.device)
                outputs = self.model(images)
                loss += criterion(outputs, labels).item()
                correct += (outputs.argmax(1) == labels).sum().item()

        accuracy = correct / len(self.trainloader.dataset)
        print(f"[Cliente {self.node_id}] Evaluate: Loss={loss}, Acc={accuracy}")
        return float(loss), len(self.trainloader.dataset), {"accuracy": float(accuracy)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", type=int, required=True, help="ID deste cliente")
    parser.add_argument("--num-nodes", type=int, required=True, help="Total de clientes")
    args = parser.parse_args()

    print(f"[Cliente {args.node_id}] Iniciando...")
    client = MNISTClient(node_id=args.node_id, num_nodes=args.num_nodes).to_client()
    fl.client.start_client(server_address="0.0.0.0:8080", client=client)