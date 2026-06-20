# CryptoFL — Setup local completo (confirmado em 2026-06-19)

Ambiente 100% local. Sem ETH real, sem Pinata, sem conta externa.
Gas medido: **0.00004964 ETH** (simulado). Accuracy final: **97.29%**.

Stack confirmado:

- Hardhat 3.x (blockchain em memória, chainId 31337)
- IPFS Kubo v0.29+ (daemon local, porta API 5001, gateway 8088)
- Flower 1.7.0 (servidor na porta 8080)
- Python 3.10+ com virtualenv

---

## Pré-requisitos — verificar antes de começar

```
node --version        # precisa 18+ (22 LTS recomendado; 23 funciona com warnings)
python --version      # precisa 3.8+
npx hardhat --version # precisa 3.x
ipfs --version        # ver Passo 1 se não estiver instalado
```

---

## Passo 1 — Instalar IPFS Kubo (se ainda não tiver)

### macOS

```
brew install ipfs
```

### Linux (Ubuntu/Debian)

```
wget https://dist.ipfs.tech/kubo/v0.29.0/kubo_v0.29.0_linux-amd64.tar.gz
tar -xvzf kubo_v0.29.0_linux-amd64.tar.gz
sudo bash kubo/install.sh
```

### Inicializar (apenas uma vez por máquina)

```
ipfs init
```

Esperado: `generating ED25519 keypair... peer identity: 12D3KooW...`

---

## Passo 2 — Resolver conflito de porta

O servidor Flower usa a porta **8080**. O gateway IPFS também usa **8080** por padrão.
Mover o gateway IPFS para **8088** antes de qualquer coisa:

```
ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8088
```

Verificar:

```
ipfs config Addresses.Gateway
# deve retornar: /ip4/0.0.0.0/tcp/8088
```

> Este comando só precisa ser executado uma vez. A configuração fica salva
> em `~/.ipfs/config`.

---

## Passo 3 — Criar o `.env`

Na raiz do projeto:

```
cp .env.example .env
```

Substituir o conteúdo de `.env` por:

```
RPC_URL=http://127.0.0.1:8545
PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
CHAIN_ID=31337

DAO_ABI_PATH=artifacts/contracts/DAO.sol/DAO.json
JOB_ABI_PATH=artifacts/contracts/JobContract.sol/JobContract.json
DAO_ADDRESS=
JOB_ADDRS=
JOB_ADDR=
DEPLOYMENTS_DIR=deployments
IGNITION_DIR=ignition/deployments

IPFS_API_URL=http://127.0.0.1:5001
IPFS_GATEWAYS=http://127.0.0.1:8088/ipfs/
PINATA_JWT=
PINATA_GATEWAY=https://gateway.pinata.cloud/ipfs/

ROUNDS=3
MIN_CLIENTS=3
SAVE_METRICS=true
METRICS_FILE=results/server_metrics.json
BASELINE_METRICS_FILE=results/baseline_metrics.json
BASELINE_SERVER_ADDRESS=0.0.0.0:8081

MODEL=mnistnet
DATASET=mnist
DIRICHLET_ALPHA=0.5
SEED=42

DETECT_ANOMALIES=true
NORM_THRESHOLD_STD=2.0
SKIP_IPFS=false

MALICIOUS=false
ATTACK_TYPE=label_flip
ATTACK_PROB=1.0

SEPOLIA_RPC_URL=
SEPOLIA_PRIVATE_KEY=
OPTIMISM_RPC_URL=
OPTIMISM_PRIVATE_KEY=
ARBITRUM_RPC_URL=
ARBITRUM_PRIVATE_KEY=
BASE_RPC_URL=
BASE_PRIVATE_KEY=
LOCAL_RPC_URL=http://127.0.0.1:8545
```

---

## Passo 4 — Compilar os contratos

```
npm install
npx hardhat compile
```

Esperado:

```
Compiled 6 Solidity files successfully
```

Verificar artefatos:

```
ls artifacts/contracts/DAO.sol/DAO.json
ls artifacts/contracts/JobContract.sol/JobContract.json
```

---

## Passo 5 — Abrir 5 terminais

A partir daqui cada serviço fica em seu próprio terminal.
Todos devem estar na raiz do projeto com o virtualenv ativo.

```
# Em cada terminal:
cd /caminho/para/CryptoFL
source venv/bin/activate   # ou venv\Scripts\activate no Windows
```

---

## Terminal 1 — IPFS daemon

```
ipfs daemon
```

Aguardar:

```
Daemon is ready
```

Teste rápido em outro terminal:

```
echo "ok" | ipfs add -q
# deve retornar um CID como: QmZbj5...
```

---

## Terminal 2 — Hardhat node

```
npx hardhat node
```

Aguardar:

```
Started HTTP and WebSocket JSON-RPC server at http://127.0.0.1:8545
```

Teste rápido:

```
curl -s -X POST http://127.0.0.1:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
# deve retornar: {"result":"0x0",...}
```

---

## Terminal 3 — Deploy dos contratos

Com Terminais 1 e 2 rodando:

```
# Deploy do DAO
npx hardhat run scripts/deploy-dao.ts --network localhost
```

Esperado:

```
DAO deployed at: 0x5FbDB2315678afecb367f032d93F642f64180aa3
Saved deployment info to deployments/dao-31337.json
```

```
# Criar JobContract e financiar escrow (0.003 ETH fictício)
python -m flower_fl.deploy_job
```

Esperado no final:

```
>>> FASE 2 COMPLETA! JOB CRIADO E FINANCIADO! <<<
O endereço do JobContract é: 0x...
.env atualizado. Pronto para a FASE 3.
```

Confirmar que o `.env` foi atualizado:

```
grep "JOB_ADDRS\|JOB_ADDR" .env
# deve mostrar endereços reais, não vazios
```

---

## Terminal 4 — Servidor FL

```
python -m flower_fl.server
```

Aguardar publicação do modelo inicial:

```
INICIALIZANDO MODELO GLOBAL
[2/3] Publicando no IPFS...
 ✓ CID: Qm...
[3/3] Registrando on-chain...
   Gas: 0.00002707 ETH
```

Se aparecer o CID e o gas, está tudo funcionando.

---

## Terminal 5 — Três clientes (três sub-terminais ou background)

```
# Sub-terminal A
NODE_ID=0 NUM_NODES=3 python -m flower_fl.client

# Sub-terminal B
NODE_ID=1 NUM_NODES=3 python -m flower_fl.client

# Sub-terminal C
NODE_ID=2 NUM_NODES=3 python -m flower_fl.client
```

Cada round vai:

1. Baixar modelo global do IPFS local (via CID)
2. Treinar no MNIST (~50–80s por round dependendo da máquina)
3. Publicar update no IPFS local
4. Registrar CID on-chain (Hardhat, gas fictício)

---

## Verificação final

```
python -c "
import json
d = json.load(open('results/server_metrics.json'))
print(f'Rounds:   {d[\"total_rounds\"]}')
print(f'Accuracy: {d[\"final_accuracy\"]:.4f}')
print(f'Gas:      {d[\"total_gas_eth\"]:.8f} ETH')
for r in d['rounds']:
    if r['round'] == 0: continue
    cid = (r.get('ipfs_cid') or 'null')[:24]
    print(f'  Round {r[\"round\"]}: acc={r.get(\"accuracy\",0):.4f}  gas={r.get(\"gas_eth\",0):.8f}  cid={cid}...')
assert d['total_gas_eth'] > 0
assert d['final_accuracy'] > 0.8
print('OK')
"
```

Resultado esperado (baseado na execução confirmada):

```
Rounds:   3
Accuracy: 0.9729
Gas:      0.00004964 ETH
  Round 1: acc=0.9072  gas=0.00001349  cid=QmcuQTEF4uEfwKGF634c...
  Round 2: acc=0.9633  gas=0.00001024  cid=QmUHYaXx6iMB5HTwgPZF...
  Round 3: acc=0.9729  gas=0.00000941  cid=QmQdewSjm1LPdaycEPr5...
OK
```

---

## Gerar plots

```
python plot_results.py
```

Em modo full são gerados 12 PNGs (inclui `plot_gas_breakdown.png` e
`plot_update_norms.png`, que não aparecem em modo baseline).

```
ls results/*.png results/figures/*.png 2>/dev/null | wc -l
# esperado: 12+
```

---

## Reiniciar do zero

```
# 1. Parar todos os processos (Ctrl+C em cada terminal)
# 2. Limpar estado anterior
rm -f deployments/dao-31337.json
# 3. Limpar JOB_ADDRS e JOB_ADDR do .env
sed -i '' 's/^JOB_ADDRS=.*/JOB_ADDRS=/' .env   # macOS
sed -i '' 's/^JOB_ADDR=.*/JOB_ADDR=/'   .env   # macOS
# Linux: remover as aspas simples: sed -i 's/...'
# 4. Reiniciar a partir do Terminal 2 (Hardhat node)
```

---

## Solução de problemas

| Erro | Causa | Solução |
|---|---|---|
| `Connection refused 8545` | Hardhat não está rodando | Iniciar Terminal 2 |
| `IPFS API URL not configured` | IPFS daemon parado | Iniciar Terminal 1 |
| `Contract not found` | Deploy não concluído | Verificar `deployments/dao-31337.json` |
| `JOB_ADDR não encontrado` | `deploy_job.py` não terminou | Rodar novamente Terminal 3 |
| Gateway IPFS conflita com Flower | Porta 8080 em uso | Passo 2 já resolve |
| `TypeError: unsupported operand None` | Bug antigo de `plot_results.py` | Já corrigido (Sprint 4) |
| Warning Node.js 23 no Hardhat | Versão não-LTS | Ignorar; funciona normalmente |

---

## Diferença entre local e Arbitrum Sepolia

| Aspecto | Local (Hardhat) | Arbitrum Sepolia |
|---|---|---|
| ETH | Fictício | ETH de testnet (faucet) |
| Gas units | Idênticos | Idênticos |
| Gas price | Simulado | Real (wei) |
| IPFS | Daemon local | Pinata (cloud) |
| Persistência | Perdida ao reiniciar | Permanente |
| Latência por tx | ~0ms | 2–10s |

> Para o paper: o número de **unidades de gas** por operação é idêntico
> entre o Hardhat local e a Arbitrum Sepolia real. A conversão para ETH
> usa o mesmo cálculo (`gas_used × gas_price / 1e18`). Os valores citados
> no paper são, portanto, válidos como estimativa de custo real na L2.
