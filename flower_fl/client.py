import flwr as fl
import os
import random
import torch
import torch.nn as nn
import time
import numpy as np

from .models import get_model
from .datasets import load_mnist, load_dataset
from .ipfs import ipfs_get_numpy, ipfs_add_numpy, content_hash_numpy
from .utils import USE_IPFS, USE_ONCHAIN
# NOTE: `.onchain_job` (web3 + asserts on RPC_URL/PRIVATE_KEY/JOB_ABI_PATH) is
# imported lazily inside fit() so that baseline / no_ipfs clients that do not
# anchor on-chain run without an RPC endpoint or a deployed contract.
#
# USE_IPFS / USE_ONCHAIN são INDEPENDENTES (ver ablação): `no_ipfs` usa
# USE_IPFS=false + USE_ONCHAIN=true — os pesos vão pelo protocolo Flower e um
# hash de conteúdo do update é ancorado on-chain.

JOB_ADDR = os.getenv("JOB_ADDR")
# A ancoragem on-chain (modos no_ipfs/full) exige um JobContract deployado.
if USE_ONCHAIN:
    assert JOB_ADDR, "JOB_ADDR não encontrado no .env (necessário para USE_ONCHAIN=true)"

DATASET_NAME = os.getenv("DATASET", "mnist")
MODEL_NAME = os.getenv("MODEL", "mnistnet")
ALPHA = float(os.getenv("DIRICHLET_ALPHA", "0.5"))

MALICIOUS = os.getenv("MALICIOUS", "false").lower() == "true"
ATTACK_TYPE = os.getenv("ATTACK_TYPE", "label_flip")  # "label_flip" | "noise" | "zero"
ATTACK_PROB = float(os.getenv("ATTACK_PROB", "1.0"))
SCALE_GAMMA = float(os.getenv("SCALE_GAMMA", "5.0"))

_NUM_CLASSES_BY_DATASET = {"mnist": 10, "cifar10": 10}
_VALID_ATTACKS = {"label_flip", "noise", "zero", "scaling"}


class MNISTClient(fl.client.NumPyClient):
    def __init__(self, node_id, num_nodes):
        self.node_id = node_id
        self.model = get_model(MODEL_NAME)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        print(f"[Cliente {node_id}] Modelo={MODEL_NAME}  Dataset={DATASET_NAME}")
        if MALICIOUS:
            print(f"[Cliente {node_id}] ⚠ MODO MALICIOSO ATIVO: {ATTACK_TYPE} (prob={ATTACK_PROB})")
        self.trainloader, self.testloader = load_dataset(
            DATASET_NAME, node_id, num_nodes, alpha=ALPHA,
        )

        print(f"[Cliente {node_id}] Treino: {len(self.trainloader.dataset)} amostras")
        print(f"[Cliente {node_id}] Teste:  {len(self.testloader.dataset)} amostras")

    def _apply_attack(self, images, labels):
        """Envenena (images, labels) localmente quando MALICIOUS=true.

        Tipos suportados:
          - label_flip: labels = (num_classes - 1) - labels
          - noise:      images = torch.randn_like(images)
          - zero:       images = torch.zeros_like(images)
        Retorna o par sem alteração se não estiver em modo malicioso, se a
        amostra (Bernoulli ATTACK_PROB) não for selecionada, ou se o tipo for
        desconhecido (com aviso).
        """
        if not MALICIOUS:
            return images, labels
        if random.random() > ATTACK_PROB:
            return images, labels

        if ATTACK_TYPE == "label_flip":
            num_classes = _NUM_CLASSES_BY_DATASET.get(DATASET_NAME.lower(), 10)
            labels = (num_classes - 1) - labels
            return images, labels
        if ATTACK_TYPE == "noise":
            return torch.randn_like(images), labels
        if ATTACK_TYPE == "zero":
            return torch.zeros_like(images), labels
        if ATTACK_TYPE == "scaling":
            # Scaling attack atua no update final do modelo, nao nos batches.
            return images, labels

        if ATTACK_TYPE not in _VALID_ATTACKS:
            print(f"[Cliente {self.node_id}] ⚠ ATTACK_TYPE desconhecido: '{ATTACK_TYPE}' — ignorando ataque")
        return images, labels

    def get_parameters(self, config):
        if "cid_global" in config:
            if not USE_IPFS:
                print(f"[Cliente {self.node_id}] Sem IPFS: usando params do Flower")
            else:
                cid = config["cid_global"]
                print(f"[Cliente {self.node_id}] Baixando modelo global: {cid}")
                params = ipfs_get_numpy(cid)
                self.set_parameters(params)
        return [val.cpu().numpy() for _, val in self.model.state_dict().items()]

    def set_parameters(self, parameters):
        params_dict = zip(self.model.state_dict().keys(), parameters)
        state_dict = {k: torch.tensor(v) for k, v in params_dict}
        self.model.load_state_dict(state_dict, strict=True)

    def fit(self, parameters, config):
        initial_global_params = [np.array(p, copy=True) for p in parameters]
        # Tempo de download/sincronização do modelo global para o cliente.
        _download_t0 = time.time()
        if USE_IPFS and "cid_global" in config:
            cid = config["cid_global"]
            global_params = ipfs_get_numpy(cid)
            self.set_parameters(global_params)
        else:
            self.set_parameters(parameters)
        download_time_s = time.time() - _download_t0

        optimizer = torch.optim.Adam(self.model.parameters())
        criterion = nn.NLLLoss()
        self.model.train()
        self.model.to(self.device)

        server_round = config.get("server_round", "?")
        epochs = int(config.get("epochs", 1))

        total_loss = 0.0
        batch_count = 0
        correct_predictions = 0
        total_samples = 0
        start_time = time.time()

        print(f"[Cliente {self.node_id}] Rodada {server_round}: Iniciando treino...")

        for _ in range(epochs):
            for images, labels in self.trainloader:
                images, labels = images.to(self.device), labels.to(self.device)
                images, labels = self._apply_attack(images, labels)

                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                batch_count += 1
                correct_predictions += (outputs.argmax(1) == labels).sum().item()
                total_samples += labels.size(0)

        train_time = time.time() - start_time
        avg_loss = total_loss / batch_count if batch_count else 0.0
        train_accuracy = (
            correct_predictions / total_samples if total_samples > 0 else 0.0
        )

        updated_params = [val.cpu().numpy() for _, val in self.model.state_dict().items()]

        if MALICIOUS and ATTACK_TYPE == "scaling":
            if random.random() <= ATTACK_PROB:
                scaled_params = []
                for w_global, w_local in zip(initial_global_params, updated_params):
                    delta = w_local - w_global
                    scaled_params.append(w_global + SCALE_GAMMA * delta)
                updated_params = scaled_params
                print(
                    f"[Cliente {self.node_id}] Scaling attack aplicado "
                    f"(gamma={SCALE_GAMMA:.3f})"
                )
            else:
                print(
                    f"[Cliente {self.node_id}] Scaling attack NAO aplicado "
                    f"(prob={ATTACK_PROB})"
                )
        cid_up = None
        tx_hash = None
        upload_ipfs_time_s = 0.0
        blockchain_tx_time_s = 0.0

        # Camada de ARMAZENAMENTO (IPFS) — opcional (USE_IPFS). Sem IPFS, usa um
        # hash de conteúdo determinístico do update como referência on-chain.
        content_ref = None
        if USE_IPFS:
            _upload_t0 = time.time()
            cid_up = ipfs_add_numpy(
                updated_params,
                f"update_client{self.node_id}_r{server_round}.npz",
            )
            upload_ipfs_time_s = time.time() - _upload_t0
            content_ref = cid_up
            print(f"[Cliente {self.node_id}] Publicando update no IPFS: {cid_up}")
        elif USE_ONCHAIN:
            content_ref = content_hash_numpy(updated_params)

        # Camada de ANCORAGEM (on-chain) — opcional (USE_ONCHAIN).
        if USE_ONCHAIN:
            try:
                from .onchain_job import job_send_update  # import tardio
                _tx_t0 = time.time()
                r = job_send_update(JOB_ADDR, content_ref)
                blockchain_tx_time_s = time.time() - _tx_t0
                tx_hash = r.get("hash")
                print(f"[Cliente {self.node_id}] Update ancorado on-chain: tx={tx_hash}")
            except Exception as e:
                print(f"[Cliente {self.node_id}] ERRO na blockchain: {e}")
        else:
            print(f"[Cliente {self.node_id}] Sem on-chain: update via protocolo Flower")

        # Monta dicionário de métricas somente com tipos válidos
        metrics = {
            "avg_loss": float(avg_loss),
            "batches": int(batch_count),
            "loss": float(avg_loss),
            "accuracy": float(train_accuracy),
            "train_time": float(train_time),
            "download_time_s": float(download_time_s),
            "upload_ipfs_time_s": float(upload_ipfs_time_s),
            "blockchain_tx_time_s": float(blockchain_tx_time_s),
            "round_total_client_time_s": float(
                download_time_s + train_time + upload_ipfs_time_s + blockchain_tx_time_s
            ),
            "train_samples": int(total_samples),
            "epochs": int(epochs),
            "node_id": int(self.node_id),
            "is_malicious": int(MALICIOUS),
            "attack_type": ATTACK_TYPE if MALICIOUS else "none",
        }
        # Só adiciona cid/tx_hash se existirem (ConfigsRecord do Flower rejeita None)
        if cid_up is not None:
            metrics["cid"] = cid_up
        if tx_hash is not None:
            metrics["tx_hash"] = str(tx_hash)

        return updated_params, len(self.trainloader.dataset), metrics

    def evaluate(self, parameters, config):
        self.set_parameters(parameters)
        self.model.eval()
        self.model.to(self.device)

        loss, correct = 0.0, 0
        criterion = nn.NLLLoss()

        with torch.no_grad():
            for images, labels in self.testloader:
                images, labels = images.to(self.device), labels.to(self.device)
                outputs = self.model(images)
                loss += criterion(outputs, labels).item()
                correct += (outputs.argmax(1) == labels).sum().item()

        accuracy = correct / len(self.testloader.dataset)
        print(f"[Cliente {self.node_id}] Evaluate: Acc={accuracy:.4f}")

        return float(loss), len(self.testloader.dataset), {
            "accuracy": float(accuracy),
            "node_id": int(self.node_id),
        }


if __name__ == "__main__":
    NODE_ID = int(os.getenv("NODE_ID", "0"))
    NUM_NODES = int(os.getenv("NUM_NODES", "3"))

    _seed = os.getenv("SEED")
    if _seed is not None:
        try:
            from .utils import set_seed
            set_seed(int(_seed))
        except ValueError:
            pass

    print(f"\n{'=' * 70}")
    print(f" CLIENTE {NODE_ID}/{NUM_NODES - 1}")
    print(f"{'=' * 70}\n")

    client = MNISTClient(node_id=NODE_ID, num_nodes=NUM_NODES).to_client()
    time.sleep(2)  # pequeno delay para garantir que o servidor esteja pronto
    fl.client.start_client(server_address="0.0.0.0:8080", client=client)
