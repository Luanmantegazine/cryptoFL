import os

os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import sys
import json
from datetime import datetime
from pathlib import Path

import flwr as fl
from flwr.common import parameters_to_ndarrays

from .models import MNISTNet
from .onchain_job import job_update_global
from .ipfs import ipfs_add_numpy
from .utils import ROUNDS

# Configurações
JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]
SAVE_METRICS = os.getenv("SAVE_METRICS", "true").lower() == "true"
METRICS_FILE = os.getenv("METRICS_FILE", "results/server_metrics.json")

if not JOB_ADDRS:
    raise RuntimeError("Configure JOB_ADDRS no .env")


class MetricsCollector:
    def __init__(self, job_addrs):
        self.metrics = {
            'experiment_start': datetime.now().isoformat(),
            'job_addresses': job_addrs,
            'total_rounds': ROUNDS,
            'rounds': [],
            'total_gas_eth': 0.0,
        }

    def log_round(self, round_num, gas_fee, cid, tx_hash, num_clients, failures):
        self.metrics['rounds'].append({
            'round': round_num,
            'timestamp': datetime.now().isoformat(),
            'num_clients': num_clients,
            'num_failures': failures,
            'gas_eth': gas_fee,
            'tx_hash': tx_hash,
            'ipfs_cid': cid,
        })
        self.metrics['total_gas_eth'] += gas_fee

    def save(self):
        if not SAVE_METRICS:
            return

        self.metrics['experiment_end'] = datetime.now().isoformat()
        Path(METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)

        with open(METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        print(f"\n Métricas salvas: {METRICS_FILE}")
        print(f" Gas total: {self.metrics['total_gas_eth']:.8f} ETH")


class BlockchainFLStrategy(fl.server.strategy.FedAvg):

    def __init__(self, min_clients=3):
        super().__init__(
            fraction_fit=1.0,
            fraction_evaluate=0.0,
            min_fit_clients=min_clients,
            min_evaluate_clients=min_clients,
            min_available_clients=min_clients,
        )

        self.metrics = MetricsCollector(JOB_ADDRS)
        self.latest_cid = None
        self._initialize_global_model()

    def _initialize_global_model(self):
        print("\n" + "=" * 70)
        print(" INICIALIZANDO MODELO GLOBAL")
        print("=" * 70)

        try:
            print("[1/3] Criando MNISTNet...")
            model = MNISTNet()
            initial_params = [val.cpu().numpy() for _, val in model.state_dict().items()]
            print(f"      ✓ {len(initial_params)} camadas")

            print("[2/3] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(initial_params, "global_round0.npz")
            print(f"      ✓ CID: {self.latest_cid}")

            print("[3/3] Registrando on-chain...")
            for idx, addr in enumerate(JOB_ADDRS, 1):
                result = job_update_global(addr, self.latest_cid)
                print(f"      ✓ Job {idx}: {addr[:10]}...")
                print(f"        Tx: {result['hash']}")
                print(f"        Gas: {result['gasETH']:.8f} ETH")

                self.metrics.log_round(0, result['gasETH'], self.latest_cid,
                                       result['hash'], 0, 0)

            print("\nModelo inicial publicado!\n")

        except Exception as e:
            print(f"\n ERRO: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # ✅ CORREÇÃO: Use 'server_round' e 'parameters' (obrigatório no Flower v1.8+)
    def configure_fit(self, server_round, parameters, client_manager):

        # Chama a implementação pai
        instructions = super().configure_fit(server_round, parameters, client_manager)

        # Injeta o CID no config de cada cliente
        for _, fit_ins in instructions:
            fit_ins.config.setdefault("cid_global", self.latest_cid)
            fit_ins.config.setdefault("epochs", 1)
            fit_ins.config.setdefault("server_round", server_round)

        return instructions

    # ✅ CORREÇÃO: Use 'server_round' (obrigatório no Flower v1.8+)
    def aggregate_fit(self, server_round, results, failures):
        print(f"\n{'=' * 70}")
        print(f" ROUND {server_round}/{ROUNDS}")
        print(f"{'=' * 70}")
        print(f" Resultados: {len(results)} sucesso, {len(failures)} falhas")

        # Chamar método pai
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )

        if aggregated_parameters is None:
            print(" Nenhum parâmetro agregado")
            return None, {}

        try:
            # Converter para numpy
            aggregated_ndarrays = parameters_to_ndarrays(aggregated_parameters)

            # IPFS
            print(f"\n[1/2] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(
                aggregated_ndarrays,
                f"global_round{server_round}.npz"
            )
            print(f"      ✓ CID: {self.latest_cid}")

            # Blockchain
            print(f"[2/2] Registrando on-chain...")
            total_gas = 0.0

            for idx, addr in enumerate(JOB_ADDRS, 1):
                result = job_update_global(addr, self.latest_cid)
                gas_fee = result['gasETH']
                print(f"      ✓ Job {idx}: Gas {gas_fee:.8f} ETH")
                total_gas += gas_fee

                if idx == 1:
                    self.metrics.log_round(
                        server_round, gas_fee, self.latest_cid,
                        result['hash'], len(results), len(failures)
                    )

            print(f"\n Round {server_round} concluído!")
            print(f" Gas: {total_gas:.8f} ETH")

        except Exception as e:
            print(f"\n ERRO: {e}")
            import traceback
            traceback.print_exc()

        return aggregated_parameters, aggregated_metrics


def main():
    print("\n" + "=" * 70)
    print(" FLOWER FEDERATED LEARNING SERVER")
    print("=" * 70)
    print(f" Endereço: 0.0.0.0:8080")
    print(f" Rounds: {ROUNDS}")
    print(f" Jobs: {', '.join([addr[:10] + '...' for addr in JOB_ADDRS])}")
    print(f" Salvar métricas: {SAVE_METRICS}")
    print("=" * 70 + "\n")

    # Configurar número mínimo de clientes
    min_clients = int(os.getenv("MIN_CLIENTS", "1"))
    print(f" Configuração: MIN_CLIENTS={min_clients}\n")

    # Criar estratégia
    strategy = BlockchainFLStrategy(min_clients=min_clients)

    # Configuração do servidor
    config = fl.server.ServerConfig(
        num_rounds=ROUNDS,
        round_timeout=None,
    )

    try:
        print(" Servidor iniciando... (aguardando clientes)\n")

        fl.server.start_server(
            server_address="0.0.0.0:8080",
            strategy=strategy,
            config=config,
            grpc_max_message_length=536870912,
        )

        # Experimento concluído
        print("\n" + "=" * 70)
        print(" EXPERIMENTO CONCLUÍDO COM SUCESSO!")
        print("=" * 70)

        # Salvar métricas finais
        strategy.metrics.save()

    except KeyboardInterrupt:
        print("\n\n Servidor interrompido pelo usuário")
        strategy.metrics.save()
    except Exception as e:
        print(f"\n ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
        strategy.metrics.save()
        sys.exit(1)


if __name__ == "__main__":
    main()