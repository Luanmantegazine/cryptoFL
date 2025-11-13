import os

os.environ["GRPC_POLL_STRATEGY"] = "poll"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

import sys
import json

from datetime import datetime
from pathlib import Path

import flwr as fl
from flwr.common import parameters_to_ndarrays


from models import MNISTNet
from onchain_job import job_update_global
from ipfs import ipfs_add_numpy
from utils import ROUNDS

# Configurações
JOB_ADDRS = [x.strip() for x in os.getenv("JOB_ADDRS", "").split(",") if x.strip()]
SAVE_METRICS = os.getenv("SAVE_METRICS", "true").lower() == "true"
METRICS_FILE = os.getenv("METRICS_FILE", "results/server_metrics.json")

if not JOB_ADDRS:
    raise RuntimeError(
        " ERRO: Configure JOB_ADDRS no .env\n"
        "Exemplo: JOB_ADDRS=0xeEBe00Ac0756308ac4AaBfD76c05c4F3088B8883"
    )


class MetricsCollector:

    def __init__(self, job_addrs):
        self.metrics = {
            'experiment_start': datetime.now().isoformat(),
            'job_addresses': job_addrs,
            'total_rounds': ROUNDS,
            'rounds': [],
            'gas_fees': [],
            'ipfs_cids': [],
            'total_gas_eth': 0.0,
        }

    def log_round(self, round_num, gas_fee, cid, tx_hash, num_clients, failures):
        """Registra métricas de um round"""
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
        """Salva métricas em arquivo JSON"""
        if not SAVE_METRICS:
            return

        self.metrics['experiment_end'] = datetime.now().isoformat()

        # Criar diretório se não existir
        Path(METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)

        with open(METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        print(f"\nMétricas salvas em: {METRICS_FILE}")
        print(f"Gas total gasto: {self.metrics['total_gas_eth']:.8f} ETH")


class BlockchainFLStrategy(fl.server.strategy.FedAvg):

    def __init__(self, min_clients=3):
        # Configuração Flower
        super().__init__(
            min_fit_clients=min_clients,
            min_evaluate_clients=min_clients,
            min_available_clients=min_clients,
            fraction_fit=1.0,  # Usar 100% dos clientes disponíveis
            fraction_evaluate=1.0,  # Avaliar com 100% dos clientes
        )

        self.metrics = MetricsCollector(JOB_ADDRS)
        self.latest_cid = None

        self._initialize_global_model()

    def _initialize_global_model(self):
        print("\n" + "=" * 70)
        print("INICIALIZANDO MODELO GLOBAL")
        print("=" * 70)

        try:
            # Criar modelo
            print("[1/3] Criando MNISTNet...")
            model = MNISTNet()
            initial_params = [val.cpu().numpy() for _, val in model.state_dict().items()]
            print(f"      ✓ Modelo criado: {len(initial_params)} camadas")

            # Upload para IPFS
            print("[2/3] Publicando no IPFS...")
            self.latest_cid = ipfs_add_numpy(initial_params, "global_round0.npz")
            print(f"      ✓ IPFS CID: {self.latest_cid}")

            # Registrar on-chain
            print("[3/3] Registrando on-chain...")
            for idx, addr in enumerate(JOB_ADDRS, 1):
                try:
                    result = job_update_global(addr, self.latest_cid)
                    print(f"      ✓ Job {idx}/{len(JOB_ADDRS)}: {addr[:10]}...")
                    print(f"        Tx: {result['hash']}")
                    print(f"        Gas: {result['gasETH']:.8f} ETH")

                    # Salvar métrica
                    self.metrics.log_round(0, result['gasETH'], self.latest_cid,
                                           result['hash'], 0, 0)
                except Exception as e:
                    print(f"      ✗ ERRO no Job {idx}: {e}")
                    raise

            print("\n Modelo inicial publicado com sucesso!\n")

        except Exception as e:
            print(f"\n ERRO FATAL na inicialização: {e}")
            sys.exit(1)

    def configure_fit(self, server_round, parameters, client_manager):
        """Configura clientes para round de treinamento"""
        print("\n" + "=" * 70)
        print(f" ROUND {server_round}/{ROUNDS}")
        print("=" * 70)
        print(f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Obter instruções padrão
        instructions = super().configure_fit(server_round, parameters, client_manager)

        # Adicionar configurações customizadas
        for client_proxy, fit_ins in instructions:
            fit_ins.config["cid_global"] = self.latest_cid
            fit_ins.config["server_round"] = server_round
            fit_ins.config["job_addr"] = JOB_ADDRS[0]  # Passar job address

        print(f" Enviando modelo para {len(instructions)} clientes...")
        print(f"   CID: {self.latest_cid}")
        print("")

        return instructions

    def aggregate_fit(self, server_round, results, failures):
        """Agrega resultados dos clientes e publica novo modelo"""
        print(f"\n Recebendo resultados do Round {server_round}...")
        print(f"    Sucesso: {len(results)} clientes")

        if failures:
            print(f"   ✗ Falhas: {len(failures)} clientes")
            for failure in failures:
                print(f"     - {failure}")

        # Agregação FedAvg padrão
        aggregated, metrics = super().aggregate_fit(server_round, results, failures)

        if not aggregated or not aggregated.parameters:
            print("   ️ Nenhum parâmetro agregado, pulando publicação")
            return aggregated, metrics

        # Converter para numpy arrays
        aggregated_params = parameters_to_ndarrays(aggregated.parameters)

        try:
            # Upload para IPFS
            print(f"\n[1/2] Publicando modelo agregado no IPFS...")
            self.latest_cid = ipfs_add_numpy(
                aggregated_params,
                f"global_round{server_round}.npz"
            )
            print(f"      ✓ CID: {self.latest_cid}")

            # Registrar on-chain
            print(f"[2/2] Atualizando on-chain...")
            total_gas = 0.0
            for idx, addr in enumerate(JOB_ADDRS, 1):
                result = job_update_global(addr, self.latest_cid)
                print(f"      ✓ Job {idx}: Gas {result['gasETH']:.8f} ETH")
                total_gas += result['gasETH']

                # Salvar métrica (apenas primeiro job para evitar duplicação)
                if idx == 1:
                    self.metrics.log_round(
                        server_round,
                        result['gasETH'],
                        self.latest_cid,
                        result['hash'],
                        len(results),
                        len(failures)
                    )

            print(f"\n Round {server_round} concluído!")
            print(f"💰 Gas total: {total_gas:.8f} ETH")

        except Exception as e:
            print(f"\n ERRO ao publicar round {server_round}: {e}")
            # Não interromper o experimento, continuar com próximo round

        return aggregated, metrics

    def evaluate(self, server_round, parameters):
        """Avaliação opcional do modelo global (não implementado)"""
        # Aqui você poderia avaliar o modelo global em um dataset de validação
        # Por enquanto, retornamos None para usar apenas a avaliação dos clientes
        return None


def main():
    """Função principal do servidor"""
    print("\n" + "=" * 70)
    print(" FLOWER FEDERATED LEARNING SERVER")
    print("=" * 70)
    print(f" Endereço: 0.0.0.0:8080")
    print(f" Rounds: {ROUNDS}")
    print(f" Jobs: {', '.join([addr[:10] + '...' for addr in JOB_ADDRS])}")
    print(f" Salvar métricas: {SAVE_METRICS}")
    print("=" * 70 + "\n")

    # Número mínimo de clientes (ajustável via env var)
    min_clients = int(os.getenv("MIN_CLIENTS", "3"))

    # Criar estratégia
    strategy = BlockchainFLStrategy(min_clients=min_clients)

    # Configuração do servidor
    config = fl.server.ServerConfig(
        num_rounds=ROUNDS,
        round_timeout=600.0,  # 10 minutos por round
    )

    try:
        # Iniciar servidor
        print(" Servidor iniciando... (aguardando clientes)\n")

        fl.server.start_server(
            server_address="0.0.0.0:8080",
            strategy=strategy,
            config=config,
        )

        # Experimento concluído
        print("\n" + "=" * 70)
        print(" EXPERIMENTO CONCLUÍDO COM SUCESSO!")
        print("=" * 70)

        # Salvar métricas
        strategy.metrics.save()

    except KeyboardInterrupt:
        print("\n\n⚠ Servidor interrompido pelo usuário")
        strategy.metrics.save()
    except Exception as e:
        print(f"\n ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()