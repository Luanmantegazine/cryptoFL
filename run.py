import os
import sys
import time
import signal
import subprocess
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text: str):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def get_python_executable():
    candidates = ['python3', 'python', 'py']

    for cmd in candidates:
        if shutil.which(cmd):
            try:
                result = subprocess.run(
                    [cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version_str = result.stdout + result.stderr
                if 'Python 3.' in version_str:
                    return cmd
            except Exception:
                continue

    raise RuntimeError("Python 3 não encontrado. Instale Python 3.8+")


class ExperimentRunner:
    def __init__(self, num_clients: int, rounds: int, auto_deploy: bool = True):
        self.num_clients = num_clients
        self.rounds = rounds
        self.auto_deploy = auto_deploy

        self.python_cmd = get_python_executable()
        print_info(f"Usando Python: {self.python_cmd}")

        self.server_process: Optional[subprocess.Popen] = None
        self.client_processes: List[subprocess.Popen] = []

        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

    def cleanup(self, signum=None, frame=None):
        print_warning("\n\nFinalizando experimento...")

        for i, proc in enumerate(self.client_processes):
            if proc and proc.poll() is None:
                print_info(f"Finalizando Cliente {i}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # Para servidor
        if self.server_process and self.server_process.poll() is None:
            print_info("Finalizando Servidor...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

        print_success("Experimento finalizado.")
        sys.exit(0)

    def check_environment(self):
        print_header("VERIFICANDO AMBIENTE")

        required_files = [
            ".env",
            "flower_fl/server.py",
            "flower_fl/client.py",
            "flower_fl/onchain_dao.py",
            "flower_fl/onchain_job.py",
        ]

        all_ok = True
        for file in required_files:
            if Path(file).exists():
                print_success(f"Encontrado: {file}")
            else:
                print_error(f"Faltando: {file}")
                all_ok = False

        from dotenv import load_dotenv
        load_dotenv()

        required_env = ["RPC_URL", "PRIVATE_KEY", "DAO_ABI_PATH", "JOB_ABI_PATH"]
        for var in required_env:
            if os.getenv(var):
                print_success(f"Variável de ambiente: {var}")
            else:
                print_error(f"Faltando variável: {var}")
                all_ok = False

        from dotenv import find_dotenv, set_key
        env_file = find_dotenv()
        if env_file:
            set_key(env_file, "ROUNDS", str(self.rounds))
            set_key(env_file, "MIN_CLIENTS", str(self.num_clients))
            print_success(f"Configurado: ROUNDS={self.rounds}, MIN_CLIENTS={self.num_clients}")

        if not all_ok:
            print_error("\nAmbiente incompleto. Corrija os problemas acima.")
            sys.exit(1)

        print_success("\nAmbiente OK!\n")

    def deploy_contracts(self):
        if not self.auto_deploy:
            print_warning("Deploy manual: certifique-se de que os contratos estão deployados.")
            input("Pressione ENTER para continuar...")
            return

        print_header("FASE 1: DEPLOY DE CONTRATOS")

        if not shutil.which("npx"):
            print_error("npx não encontrado. Instale Node.js e npm.")
            sys.exit(1)

        print_info("Deploying DAO contract...")
        result = subprocess.run(
            ["npx", "hardhat", "run", "scripts/deploy-dao.ts", "--network", "localhost"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print_success("DAO deployado com sucesso!")
            print(result.stdout)
        else:
            print_error("Erro no deploy do DAO:")
            print(result.stderr)
            sys.exit(1)

        print_header("FASE 2: CRIANDO JOB CONTRACT")

        print_info("Criando JobContract...")
        result = subprocess.run(
            [self.python_cmd, "-m", "flower_fl.deploy-job"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print_success("JobContract criado com sucesso!")
            print(result.stdout)
        else:
            print_error("Erro na criação do JobContract:")
            print(result.stderr)
            sys.exit(1)

        time.sleep(2)

    def start_server(self):
        print_header("FASE 3: INICIANDO SERVIDOR FLOWER")

        log_file = self.logs_dir / f"server_{self.timestamp}.log"
        log_handle = open(log_file, "w")

        print_info(f"Iniciando servidor (log: {log_file})...")

        self.server_process = subprocess.Popen(
            [self.python_cmd, "-m", "flower_fl.server"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )

        print_info("Aguardando servidor inicializar...")

        server_ready = False
        timeout = 30
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.server_process.poll() is not None:
                print_error("Servidor falhou ao iniciar. Verificando log...")
                with open(log_file, "r") as f:
                    print(f.read())
                sys.exit(1)

            if log_file.exists():
                with open(log_file, "r") as f:
                    log_content = f.read()
                    if "Servidor iniciando" in log_content or "Flower server" in log_content:
                        server_ready = True
                        break

            time.sleep(0.5)
            print(".", end="", flush=True)

        print()

        if not server_ready:
            print_warning("Timeout aguardando servidor. Continuando mesmo assim...")
            time.sleep(5)
        else:
            print_success("Servidor inicializado!")
            time.sleep(2)

        if self.server_process.poll() is None:
            print_success(f"Servidor rodando (PID: {self.server_process.pid})")
        else:
            print_error("Servidor falhou ao iniciar. Verifique o log.")
            sys.exit(1)

    def start_clients(self):
        print_header(f"FASE 4: INICIANDO {self.num_clients} CLIENTES FLOWER")

        for i in range(self.num_clients):
            log_file = self.logs_dir / f"client_{i}_{self.timestamp}.log"
            log_handle = open(log_file, "w")

            print_info(f"Iniciando Cliente {i} (log: {log_file})...")

            env = os.environ.copy()
            env["NODE_ID"] = str(i)
            env["NUM_NODES"] = str(self.num_clients)

            client_process = subprocess.Popen(
                [self.python_cmd, "-m", "flower_fl.client"],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=1,
                universal_newlines=True
            )

            self.client_processes.append(client_process)

            time.sleep(2)

        print_success(f"{self.num_clients} clientes iniciados!")

    def monitor_experiment(self):
        print_header("MONITORANDO EXPERIMENTO")

        print_info(f"Servidor rodando (PID: {self.server_process.pid})")
        for i, proc in enumerate(self.client_processes):
            print_info(f"Cliente {i} rodando (PID: {proc.pid})")

        print("\n" + "=" * 70)
        print("Logs sendo escritos em tempo real em: ./logs/")
        print(f"  - server_{self.timestamp}.log")
        for i in range(self.num_clients):
            print(f"  - client_{i}_{self.timestamp}.log")
        print("\nPressione Ctrl+C para finalizar o experimento")
        print("=" * 70 + "\n")

        try:
            print_info("Aguardando conclusão do servidor...")
            self.server_process.wait()
            print_success("Servidor finalizou!")
        except KeyboardInterrupt:
            print_warning("\nInterrompido pelo usuário.")

        # Aguarda clientes terminarem (ou timeout de 30s)
        print_info("Aguardando clientes finalizarem...")
        for i, proc in enumerate(self.client_processes):
            try:
                proc.wait(timeout=30)
                print_success(f"Cliente {i} finalizou!")
            except subprocess.TimeoutExpired:
                print_warning(f"Cliente {i} timeout - finalizando...")
                proc.kill()

    def show_results(self):
        print_header("RESULTADOS DO EXPERIMENTO")

        metrics_file = Path(os.getenv("METRICS_FILE", "results/server_metrics.json"))

        if metrics_file.exists():
            import json
            with open(metrics_file, "r") as f:
                metrics = json.load(f)

            print_success("Métricas salvas em: " + str(metrics_file))
            print()
            print(f"  Total de Rounds: {metrics['total_rounds']}")
            print(f"  Gas Total: {metrics['total_gas_eth']:.8f} ETH")
            print(f"  Job Addresses: {', '.join([addr[:10] + '...' for addr in metrics['job_addresses']])}")
            print()

            print("  Detalhes por Round:")
            for round_data in metrics['rounds']:
                print(f"    Round {round_data['round']}: {round_data['num_clients']} clientes, "
                      f"Gas {round_data['gas_eth']:.8f} ETH")
        else:
            print_warning("Arquivo de métricas não encontrado.")

        print()
        print_info(f"Logs salvos em: {self.logs_dir}/")
        print_info(f"  - server_{self.timestamp}.log")
        for i in range(self.num_clients):
            print_info(f"  - client_{i}_{self.timestamp}.log")

    def run(self):
        """Executa experimento completo"""
        try:
            self.check_environment()
            self.deploy_contracts()
            self.start_server()
            self.start_clients()
            self.monitor_experiment()
            self.show_results()

            print_header("EXPERIMENTO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print_error(f"\nErro durante experimento: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(
        description="Execute experimento FL com múltiplos clientes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python3 -m run --clients 3 --rounds 3
  python3 -m run --clients 5 --rounds 5 --no-deploy
  python3 -m run -c 10 -r 10
        """
    )

    parser.add_argument(
        "-c", "--clients",
        type=int,
        default=3,
        help="Número de clientes FL (padrão: 3)"
    )

    parser.add_argument(
        "-r", "--rounds",
        type=int,
        default=3,
        help="Número de rounds de treinamento (padrão: 3)"
    )

    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Pula deploy de contratos (usar contratos existentes)"
    )

    args = parser.parse_args()

    # Banner
    print(f"""
{Colors.HEADER}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║              CryptoFL - Blockchain Federated Learning             ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
    """)

    print_info(f"Configuração: {args.clients} clientes, {args.rounds} rounds")
    print_info(f"Auto-deploy: {'Não' if args.no_deploy else 'Sim'}")
    print()

    runner = ExperimentRunner(
        num_clients=args.clients,
        rounds=args.rounds,
        auto_deploy=not args.no_deploy
    )

    runner.run()


if __name__ == "__main__":
    main()