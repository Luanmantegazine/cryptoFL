import subprocess
import time
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def run_experiment():
    print("--- FASE 1: Implantando Contrato DAO ---")
    subprocess.run(
        ["npx", "hardhat", "run", "scripts/deploy-dao.ts", "--network", "localhost"],
        cwd=".."
    )

    print("\n--- FASE 2: Criando Job ---")
    subprocess.run(["python", "deploy-job.py"])

    # Iniciar servidor
    print("\n--- FASE 3: Iniciando Servidor Flower ---")
    server_log = open("server.log", "w")
    server = subprocess.Popen(
        ["python", "server.py"],
        stdout=server_log,
        stderr=subprocess.STDOUT
    )
    print("Aguardando 15s para o servidor iniciar...")
    time.sleep(15)

    # Iniciar 3 clientes
    print("\n--- FASE 3: Iniciando Clientes Flower ---")
    clients = []
    client_logs = []
    num_clients = 3
    for i in range(num_clients):
        print(f"Iniciando cliente {i}...")
        log_file = open(f"client_{i}.log", "w")
        client = subprocess.Popen(
            ["python", "client.py"],
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        clients.append(client)
        client_logs.append(log_file)
        time.sleep(2)

    print(f"\n--- FASE 3: {num_clients} Clientes e Servidor estão rodando ---")
    print("Logs sendo escritos em server.log e client_*.log")
    print("Aguardando o Servidor (FL) completar...")

    server.wait()
    print("\n--- FASE 3: Servidor Flower terminou ---")
    for c in clients:
        c.wait()
    print("--- FASE 3: Clientes terminaram ---")

    # Fecha os arquivos de log
    server_log.close()
    for f in client_logs:
        f.close()

    print("\nExperimento Concluído.")
    # (A lógica de coleta de métricas precisaria ler os logs/contrato)
    return {"accuracy": 0, "gas_total": 0}


if __name__ == "__main__":
    results = run_experiment()
    # print(f"Acurácia final: {results['accuracy']}")
    # print(f"Gas total: {results['gas_total']} ETH")