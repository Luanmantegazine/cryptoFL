# Blockchain-Based Federated Learning Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Solidity](https://img.shields.io/badge/Solidity-0.8.28-363636.svg)
![Hardhat](https://img.shields.io/badge/Hardhat-3.0+-yellow.svg)
![Flower](https://img.shields.io/badge/Flower-1.7.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-red.svg)

A decentralized platform for **Federated Learning** coordinated by blockchain smart contracts, featuring automated payments, IPFS storage, and Layer-2 scalability.

[Features](#-features) • [Architecture](#-architecture) • [Installation](#-installation) • [Usage](#-usage) • [Documentation](#-documentation)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [System Requirements](#-system-requirements)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Usage Guide](#-usage-guide)
- [Smart Contracts](#-smart-contracts)
- [Evaluation & Results](#-evaluation--results)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Citation](#-citation)

---

## 🌟 Overview

**CryptoFL** is a research platform that integrates **Federated Learning** (FL) with **blockchain** to study the **cost viability** of a DAO-coordinated FL marketplace.

> **Repository:** https://github.com/luanmantegazine/CryptoFL

### Acronyms

| Acronym | Full form |
|---|---|
| FL | Federated Learning |
| IPFS | InterPlanetary File System |
| DAO | Decentralised Autonomous Organisation |
| CID | Content Identifier |
| L2 | Layer 2 (Ethereum scaling solution) |
| EVM | Ethereum Virtual Machine |
| FedAvg | Federated Averaging |
| IID | Independent and Identically Distributed |
| non-IID | Not Independent and Identically Distributed |
| DPI | Dots Per Inch |

### Contributions & Positioning

IPFS-for-storage and an L2 rollup for cheap transactions are, on their own, *engineering choices*, not a research contribution — and we do not claim them as one. We frame this work instead as a **cost-viability study of a DAO-coordinated federated-learning marketplace**: requesters post jobs, the DAO matches trainers and escrows payment, and model versions/updates are anchored on-chain by CID while FedAvg runs off-chain.

Concretely, the repository **measures**:

1. **Gas breakdown per marketplace operation** — register, offer, accept (deploy job), sign, record update, publish global model (`results/.../*_breakdown.json`, `plot_gas_breakdown`).
2. **Overhead vs. vanilla Flower** — `baseline` (Flower only) vs. `no_ipfs` (on-chain anchoring, weights over the wire) vs. `full` (IPFS + on-chain), via `ablation_experiment.py`.
3. **Matching scalability** — wall-clock and estimated gas of `DAO.matchTrainers` as the number of registered trainers grows (`scripts/load_test_matching.ts`), exposing its O(n) loop as the bottleneck.
4. **Robustness under malicious clients** — accuracy drop and anomaly-detector flags vs. the fraction of poisoning clients, with mean ± std over seeds (`security_experiment.py`).
5. **Generality beyond MNIST** — CIFAR-10 with non-IID (Dirichlet-α) partitions and a ResNet-18.

Claims are deliberately modest: this is a measurement/feasibility study of *whether* such a marketplace is economically and computationally plausible on an L2, **not** a claim of a novel consensus, aggregation, or privacy mechanism. What the blockchain does and does **not** guarantee is stated in [Security model](#-security-model) (the off-chain aggregator remains trusted).

### Key Innovations

- 🔗 **Smart Contract Coordination**: Automated job matching, contract negotiation, and payment release
- 💰 **Escrow-Based Payments**: Trustless payment guarantees with automatic release per training update
- 📦 **Decentralized Storage**: IPFS integration for model versioning without on-chain storage overhead
- ⚡ **Layer-2 Scalability**: Arbitrum rollup for low-cost transactions (~0.0001 ETH per update)
- 🔍 **Full Auditability**: Immutable record of all model updates and financial transactions

### Research Context

This project was developed as part of academic research exploring the intersection of federated learning, blockchain, and decentralized AI. A corresponding research paper is available in `Blockchain_FL_Paper.pdf`.

---

## ✨ Features

### Federated Learning
- ✅ **Flower Framework Integration**: Industry-standard FL orchestration
- ✅ **FedAvg Aggregation**: Weighted averaging of client model updates
- ✅ **Privacy-Preserving**: No raw data leaves client devices
- ✅ **Configurable Rounds**: Support for multi-round training workflows
- ✅ **Performance Metrics**: Automatic accuracy tracking and reporting

### Blockchain Layer
- ✅ **DAO-Based Governance**: Decentralized participant registration and matching
- ✅ **Job Marketplace**: Requesters post jobs, trainers accept offers
- ✅ **Automated Payments**: Funds released automatically upon verified updates
- ✅ **State Machine Contracts**: Enforced workflow from negotiation to completion
- ✅ **Event Logging**: Comprehensive on-chain audit trail

### Storage & Infrastructure
- ✅ **IPFS Integration**: Content-addressable storage for models (via Pinata)
- ✅ **Arbitrum Layer 2**: ~100x cheaper than Ethereum mainnet
- ✅ **MetaMask Support**: Standard Web3 wallet integration
- ✅ **Testnet Ready**: Full support for Arbitrum Sepolia

### Developer Experience
- ✅ **One-Command Deployment**: Automated setup script (`run.py`)
- ✅ **Real-Time Monitoring**: Live logs for server and all clients
- ✅ **Visualization Tools**: Automatic generation of cost/performance plots
- ✅ **Comprehensive Tests**: Hardhat test suite for smart contracts

---

## 🏗 Architecture

### System Overview
```
┌─────────────────────────────────────────────────────────────┐
│                     CryptoFL Platform                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │  Requester   │────────▶│   DAO.sol    │                 │
│  │  (Client)    │         │  (Matching)  │                 │
│  └──────────────┘         └──────┬───────┘                 │
│                                   │                          │
│                            creates│                          │
│                                   ▼                          │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │   Trainer    │◀───────▶│ JobContract  │                 │
│  │  (Worker)    │  signs  │   (Escrow)   │                 │
│  └──────┬───────┘         └──────┬───────┘                 │
│         │                         │                          │
│         │ runs FL                 │ records CIDs            │
│         ▼                         ▼                          │
│  ┌─────────────────────────────────────┐                   │
│  │       Flower Framework (FL)          │                   │
│  │  ┌─────────┐      ┌──────────┐     │                   │
│  │  │ Server  │◀────▶│ Client 1 │     │                   │
│  │  │ (Agg.)  │      │ Client 2 │     │                   │
│  │  └────┬────┘      │ Client N │     │                   │
│  │       │           └──────────┘     │                   │
│  └───────┼───────────────────────────┘                   │
│          │                                                  │
│          ▼                                                  │
│  ┌──────────────────┐                                     │
│  │  IPFS (Pinata)   │  Model Storage                      │
│  │  CID: bafybei... │  (Off-chain)                        │
│  └──────────────────┘                                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐ │
│  │         Arbitrum Layer 2 (Sepolia)                    │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │ │
│  │  │ DAO        │  │ Requester  │  │ Trainer    │     │ │
│  │  │ Contract   │  │ Proxy      │  │ Proxy      │     │ │
│  │  └────────────┘  └────────────┘  └────────────┘     │ │
│  │  ┌────────────────────────────────────────────┐     │ │
│  │  │      JobContract (per task)                 │     │ │
│  │  │  • Escrow: 0.003 ETH locked                │     │ │
│  │  │  • Updates: 3/3 recorded                   │     │ │
│  │  │  • Status: Fulfilled                        │     │ │
│  │  └────────────────────────────────────────────┘     │ │
│  └──────────────────────────────────────────────────────┘ │
│                          │                                  │
│                   batched & rolled up                       │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │         Ethereum Layer 1 (Mainnet)                    │ │
│  │         (Final settlement & security)                  │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Workflow Phases

#### **Phase 1: Setup (On-Chain)**
1. **Registration**: Requester and Trainer register via DAO contract
2. **Matching**: Requester searches for trainers using requirements (rating, tags, specs)
3. **Offer Creation**: Requester creates job offer with payment terms
4. **Acceptance**: Trainer accepts offer → JobContract deployed
5. **Signing**: Both parties sign + Requester deposits escrow funds

#### **Phase 2: Training (Hybrid)**
1. **Initialization**: Server publishes initial model to IPFS → records CID on-chain
2. **Distribution**: Clients download model from IPFS via CID
3. **Local Training**: Each client trains on private data
4. **Update Submission**: Clients upload updates to IPFS → record CIDs on-chain
5. **Aggregation**: Server downloads all updates, applies FedAvg
6. **Publication**: New global model published to IPFS → CID recorded
7. **Payment**: Automatic release of `valueByUpdate` per verified update
8. **Repeat**: Steps 2-7 until `numberOfUpdates` reached

---

## 💻 System Requirements

### Hardware
- **Minimum**: 4 GB RAM, 2 CPU cores, 10 GB disk
- **Recommended**: 8 GB RAM, 4 CPU cores, 20 GB disk
- **GPU**: Optional (speeds up local training)

### Software
- **Python**: 3.8+ (tested on 3.10, 3.12)
- **Node.js**: 18+ (for Hardhat)
- **npm/pnpm**: Latest stable
- **Git**: For cloning repository

### External Services
- **MetaMask**: Browser wallet for testnet
- **Pinata Account**: Free tier (IPFS pinning)
- **Arbitrum Sepolia Faucet**: For test ETH

---

## 📦 Installation

### 1. Clone Repository
```bash
git clone https://github.com/luanmantegazine/CryptoFL.git
cd CryptoFL
```

### 2. Install Python Dependencies
```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Key Python Packages:**
- `flwr==1.7.0` - Federated Learning framework
- `torch` - PyTorch for model training
- `web3==6.20.1` - Ethereum interaction
- `python-dotenv` - Environment configuration
- `requests` - IPFS API calls

### 3. Install Node.js Dependencies
```bash
npm install
# or
pnpm install
```

**Key Node Packages:**
- `hardhat` - Ethereum development environment
- `@nomicfoundation/hardhat-toolbox-viem` - Modern Ethereum tooling
- `@openzeppelin/contracts` - Secure smart contract library

### 4. Configure Environment

Copy the template and fill in values as needed:
```bash
cp .env.example .env
```

`.env` is git-ignored. **Only the `full` on-chain flow and Arbitrum deployment
need real values** — the `baseline`, `no_ipfs`, ablation and security
experiments run with zero configuration. `.env.example` documents every
variable the code reads, including `RPC_URL`, `PRIVATE_KEY`, `DAO_ABI_PATH`,
`JOB_ABI_PATH`, `PINATA_JWT`, `ROUNDS`, `MIN_CLIENTS`, `MODEL`, `DATASET`,
`DIRICHLET_ALPHA`, and the anomaly-detection / malicious-client knobs.

> ⚠ **Secrets rotation:** earlier commits of this repository included a real
> `.env` with a live `PINATA_JWT` (and a `PRIVATE_KEY`). That Pinata token must
> be **revoked and regenerated** — treat it as compromised. `.env` is now
> ignored and must never be committed; use `.env.example` as the template.

### 5. Setup Pinata (IPFS)

1. Create free account at [pinata.cloud](https://pinata.cloud)
2. Generate API JWT token (Dashboard → API Keys → New Key)
3. Add JWT to `.env` as `PINATA_JWT`

### 6. Setup MetaMask

1. Install [MetaMask](https://metamask.io) browser extension
2. Add Arbitrum Sepolia network:
   - **Network Name**: Arbitrum Sepolia
   - **RPC URL**: `https://sepolia-rollup.arbitrum.io/rpc`
   - **Chain ID**: 421614
   - **Currency**: ETH
   - **Explorer**: `https://sepolia.arbiscan.io`
3. Get test ETH from [faucet](https://faucet.quicknode.com/arbitrum/sepolia)

---

## 🚀 Quick Start

### Option 1: Automated Deployment (Recommended)

Run the entire experiment with one command:
```bash
python3 run.py --clients 3 --rounds 3
```

**What happens:**
1. ✅ Environment validation
2. ✅ Smart contract deployment (DAO + JobContract)
3. ✅ FL server initialization
4. ✅ 3 FL clients launch
5. ✅ Training for 3 rounds
6. ✅ Automatic metrics collection
7. ✅ Results visualization

### Option 2: Manual Step-by-Step

#### Terminal 1: Local Blockchain
```bash
npx hardhat node
```

#### Terminal 2: Deploy Contracts
```bash
# Deploy DAO
npx hardhat run scripts/deploy-dao.ts --network localhost

# Create JobContract
python3 -m flower_fl.deploy_job
```

#### Terminal 3: FL Server
```bash
python3 -m flower_fl.server
```

#### Terminal 4+: FL Clients
```bash
# Client 0
NODE_ID=0 NUM_NODES=3 python3 -m flower_fl.client

# Client 1 (new terminal)
NODE_ID=1 NUM_NODES=3 python3 -m flower_fl.client

# Client 2 (new terminal)
NODE_ID=2 NUM_NODES=3 python3 -m flower_fl.client
```

### View Results
```bash
python3 plot_results.py
```

Generates `experiment_results_complete.png` with:
- Gas cost analysis
- Model accuracy evolution
- Cost vs performance trade-offs

---

## � Reproducing paper results

All experiments can be reproduced without deploying contracts or using real ETH.

### Baseline only (no blockchain, no IPFS)

```bash
# Terminal 1 — server
ROUNDS=5 MIN_CLIENTS=3 python -m flower_fl.baseline_runner

# Terminals 2–4 — clients
BASELINE_AS_CLIENT=1 NODE_ID=0 NUM_NODES=3 python -m flower_fl.baseline_runner
BASELINE_AS_CLIENT=1 NODE_ID=1 NUM_NODES=3 python -m flower_fl.baseline_runner
BASELINE_AS_CLIENT=1 NODE_ID=2 NUM_NODES=3 python -m flower_fl.baseline_runner
```

### Multiple runs with variance

```bash
python multi_run.py --mode baseline --clients-list 5,10,15 --rounds 5 --repetitions 3
```

### Security experiment (no blockchain needed)

```bash
python security_experiment.py --mode baseline --clients 5 --rounds 5 \
    --malicious-pct 0.0,0.2,0.4 --attack-type label_flip
```

### Ablation study (no blockchain needed for `baseline` and `no_ipfs`)

```bash
python ablation_experiment.py --clients 3 --rounds 3
```

### Full system (requires Hardhat node + Pinata JWT)

```bash
python run.py --clients 5 --rounds 5
```

---

## 🖥 Fully local full-mode run (no real ETH, no Pinata)

You can run the **complete on-chain flow** entirely on your machine — real gas
units, real IPFS CIDs, zero cost — using a local Hardhat node + a local IPFS
(Kubo) daemon instead of Pinata. A confirmed end-to-end run produced
**gas = 0.00004964 ETH** and **final accuracy = 97.29%** over 3 rounds.

Key point: the Flower server (port `8080`) collides with the default IPFS
gateway (also `8080`). Move the IPFS gateway to `8088` once:

```bash
ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8088
```

Then set `IPFS_API_URL=http://127.0.0.1:5001` and
`IPFS_GATEWAYS=http://127.0.0.1:8088/ipfs/` (leave `PINATA_JWT=` empty) in `.env`.

See **[SETUP_LOCAL.md](SETUP_LOCAL.md)** for the full step-by-step guide
(IPFS install, port fix, `.env`, deploy, server + clients, verification, plots,
and troubleshooting).

---

## �📁 Project Structure
```
CryptoFL/
├── contracts/                  # Smart contracts
│   ├── DAO.sol                # Main orchestrator
│   ├── JobContract.sol        # Per-task escrow
│   ├── Requester.sol          # Requester proxy
│   ├── Trainer.sol            # Trainer proxy
│   └── DataTypes.sol          # Shared structs
│
├── flower_fl/                 # FL implementation
│   ├── server.py              # Aggregation server
│   ├── client.py              # Training client
│   ├── models.py              # MNISTNet architecture
│   ├── datasets.py            # Data partitioning
│   ├── onchain_dao.py         # DAO interaction
│   ├── onchain_job.py         # JobContract interaction
│   ├── ipfs.py                # IPFS utilities
│   ├── deployments.py         # Contract discovery
│   ├── deploy_job.py          # Setup automation
│   └── utils.py               # Helpers
│
├── scripts/                   # Deployment scripts
│   └── deploy-dao.ts          # DAO deployment
│
├── test/                      # Test suites
│   ├── Counter.ts             # Example tests
│   └── DAOJobCreation.ts      # Integration tests
│
├── ignition/                  # Hardhat Ignition
│   └── modules/
│       └── Counter.ts
│
├── results/                   # Experiment outputs
│   └── server_metrics.json    # Collected metrics
│
├── logs/                      # Runtime logs
│   ├── server_*.log
│   └── client_*_*.log
│
├── run.py                     # Main automation script
├── plot_results.py            # Visualization
├── hardhat.config.ts          # Hardhat configuration
├── package.json               # Node dependencies
├── requirements.txt           # Python dependencies
├── tsconfig.json              # TypeScript config
├── .gitignore                 # Git exclusions
├── .env                       # Environment variables
├── README.md                  # This file
└── Blockchain_FL_Paper.pdf    # Research paper
```

---

## ⚙️ Configuration

### Experiment Parameters

Edit `.env` or pass CLI arguments:
```bash
# Scale experiment
python3 run.py --clients 10 --rounds 5

# Skip contract deployment (use existing)
python3 run.py --no-deploy --clients 5 --rounds 3
```

### Model Hyperparameters

Edit `flower_fl/server.py` and `flower_fl/client.py`:
```python
# In client.py
BATCH_SIZE = 32
LEARNING_RATE = 0.01
LOCAL_EPOCHS = 1

# In server.py
AGGREGATION_STRATEGY = FedAvg  # Or FedProx, FedOpt, etc.
```

### Blockchain Network

Switch between networks in `hardhat.config.ts`:
```typescript
networks: {
  localhost: {
    url: "http://127.0.0.1:8545"
  },
  arbitrumSepolia: {
    url: process.env.RPC_URL,
    accounts: [process.env.PRIVATE_KEY]
  }
}
```

### IPFS Provider

Default: Pinata (recommended for testnet)

Alternative: Local IPFS node:
```bash
# In .env
IPFS_API_URL=http://127.0.0.1:5001
# Remove PINATA_JWT
```

---

## 📚 Usage Guide

### Scenario 1: Research Experiment

**Goal**: Measure cost vs accuracy trade-offs
```bash
# Run multiple configurations
for clients in 5 10 15 20 25; do
  python3 run.py --clients $clients --rounds 5
  mv results/server_metrics.json results/metrics_${clients}clients.json
done

# Compare results
python3 -c "
import json
for c in [5, 10, 15, 20, 25]:
    with open(f'results/metrics_{c}clients.json') as f:
        data = json.load(f)
        print(f'{c} clients: {data[\"total_gas_eth\"]:.6f} ETH, '
              f'Acc: {data[\"final_accuracy\"]:.2%}')
"
```

### Scenario 2: Production Deployment

**Goal**: Deploy to Arbitrum mainnet

1. Update `.env`:
```bash
RPC_URL=https://arb1.arbitrum.io/rpc
PRIVATE_KEY=your_real_private_key  # ⚠️ NEVER commit this
```

2. Fund wallet with real ETH

3. Deploy contracts:
```bash
npx hardhat run scripts/deploy-dao.ts --network arbitrum
```

4. Update `JOB_ADDR` in `.env` with deployed address

5. Run FL:
```bash
python3 -m flower_fl.server  # On server machine
python3 -m flower_fl.client  # On each trainer machine
```

### Scenario 3: Custom Model

**Goal**: Train custom architecture

1. Define model in `flower_fl/models.py`:
```python
class CustomNet(nn.Module):
    def __init__(self):
        super().__init__()
        # Your architecture here
```

2. Update `flower_fl/client.py`:
```python
from .models import CustomNet
self.model = CustomNet()
```

3. Prepare dataset in `flower_fl/datasets.py`:
```python
def load_custom_data(node_id, num_nodes):
    # Your data loading logic
    return trainloader, testloader
```

---

## 🔗 Smart Contracts

### DAO.sol

**Purpose**: Platform orchestrator

**Key Functions:**
- `registerRequester()` → Create requester profile
- `registerTrainer(desc, spec)` → Create trainer profile
- `matchTrainers(requirements)` → Find suitable trainers
- `MakeOffer(...)` → Create job offer
- `AcceptOffer(offerID)` → Accept offer → deploy JobContract
- `signJobContract(jobAddr)` → Commit to contract
- `getPendingOffers()` → View incoming offers

### JobContract.sol

**Purpose**: Per-task escrow and coordination

**Key Functions:**
- `publishGlobalModel(cidHash, encryptedCid)` → Record model version
- `recordClientUpdate(cidHash, encryptedCid)` → Record client contribution
- `releaseToTrainer(recipient)` → Withdraw earned funds
- `deposit()` → Lock escrow funds (requester)

**State Machine:**
```
WaitingSignatures → WaitingRequesterSignature
                  → WaitingTrainerSignature
                  → Signed
                  → Fulfilled
```

### Gas Costs (Arbitrum Sepolia)

| Operation | Gas Used | Cost (ETH) |
|-----------|----------|------------|
| Register Requester | ~200k | ~0.0002 |
| Register Trainer | ~250k | ~0.00025 |
| Make Offer | ~150k | ~0.00015 |
| Accept Offer (deploy Job) | ~800k | ~0.0008 |
| Sign Contract | ~100k | ~0.0001 |
| Record Update | ~80k | ~0.00008 |
| Publish Global Model | ~70k | ~0.00007 |

**Total for 3-round, 3-client experiment: ~0.003 ETH** (~$7 at $2,300/ETH)

---

## � Security model

### What blockchain guarantees in this system

Recording CIDs on-chain provides:
- **Ordering** — every global model version and client update has an immutable, timestamped sequence on-chain.
- **Auditability** — any third party can verify which CID was published in which round, by whom, and when.
- **Tamper-evidence** — once a CID is recorded, the reference cannot be changed retroactively.

### What it does NOT guarantee

- **Correctness of updates** — the blockchain stores a pointer (CID) to the update, not the update itself. A trainer can submit a poisoned update; its CID will be faithfully recorded.
- **Aggregator honesty** — FedAvg is performed off-chain by a trusted server. A malicious aggregator could publish an arbitrary global model and record a legitimate-looking CID.
- **Sybil resistance** — any address can register as a Trainer in the DAO. Without additional identity verification, a single actor can register multiple Trainers.

### Mitigations implemented

- **Norm-based anomaly detection** (`DETECT_ANOMALIES=true`): updates whose L2 norm exceeds `mean + N×std` across a round are flagged in the metrics. See `flower_fl/server.py`.
- **Malicious client simulation** (`MALICIOUS=true`): supports `label_flip`, `noise`, and `zero` attacks. See `flower_fl/client.py`.
- **Security experiment** (`security_experiment.py`): runs paired experiments (clean vs. X% malicious) and reports accuracy drop and flagged updates.

### Known limitations (future work)

- The aggregator remains a trusted party; decentralizing aggregation (e.g. via Shapley-based on-chain verification or zkML) is left as future work.
- The norm check is a heuristic and can be bypassed by a sophisticated adversary (e.g. scaling a poisoned update to match the expected norm range).
- Reputation/slashing of flagged trainers is not yet enforced on-chain; the `rating` field in `Trainer.sol` is updated manually.

---

## �📊 Evaluation & Results

### Metrics Collected

**Blockchain Metrics:**
- Gas consumption per operation
- Transaction hashes for auditability
- Cumulative cost tracking
- Cost per client efficiency

**Machine Learning Metrics:**
- Model accuracy per round
- Training loss
- Number of samples per client
- Convergence rate

### Example Results
```json
{
  "experiment_start": "2025-01-15T10:30:00",
  "experiment_end": "2025-01-15T10:45:00",
  "total_rounds": 3,
  "job_addresses": ["0x5FbDB2315678..."],
  "total_gas_eth": 0.00234567,
  "final_accuracy": 0.9234,
  "rounds": [
    {
      "round": 1,
      "num_clients": 3,
      "gas_eth": 0.00078123,
      "accuracy": 0.8456,
      "ipfs_cid": "bafybeigdyrzt5sfp7udm...",
      "tx_hash": "0x1a2b3c..."
    }
  ]
}
```

### Visualization

Run `python3 plot_results.py` to generate:

1. **Gas Cost per Round**: Track aggregation costs
2. **Cumulative Cost**: Total experiment expenditure
3. **Gas per Client**: Efficiency metric
4. **Model Accuracy Evolution**: Learning progress
5. **Cost vs Performance**: Trade-off analysis
6. **Technical Summary**: Key statistics

---

## 🐛 Troubleshooting

### Common Issues

#### 1. "Python 3 not found"
```bash
# macOS
brew install python3

# Ubuntu/Debian
sudo apt install python3 python3-pip

# Windows
# Download from python.org
```

#### 2. "Insufficient funds for gas"
- Get test ETH from [Arbitrum Sepolia faucet](https://faucet.quicknode.com/arbitrum/sepolia)
- Check balance: `npx hardhat run scripts/check-balance.ts`

#### 3. "IPFS upload failed"
- Verify `PINATA_JWT` in `.env`
- Check Pinata dashboard for rate limits
- Try alternative gateway in `PINATA_GATEWAY`

#### 4. "Contract not found"
- Ensure `deploy-dao.ts` ran successfully
- Check `deployments/dao-<chainId>.json` exists
- Verify `DAO_ADDRESS` in `.env` (if set manually)

#### 5. "Flower server won't start"
```bash
# Check port availability
lsof -i :8080  # macOS/Linux
netstat -ano | findstr :8080  # Windows

# Kill existing process
kill -9 <PID>
```

#### 6. "Clients can't connect to server"
- Ensure server is running (`logs/server_*.log`)
- Check firewall settings
- Verify `0.0.0.0:8080` in server config

### Debug Mode

Enable verbose logging:
```bash
# In .env
DEBUG=true

# Run with debug output
python3 -m flower_fl.server --verbose
```

### Getting Help

1. Check [Issues](https://github.com/your-username/CryptoFL/issues)
2. Review logs in `logs/` directory
3. Consult research paper for architecture details
4. Contact: [your-email@university.edu](mailto:your-email@university.edu)

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Run smart-contract tests (Hardhat)
npx hardhat test

# Optional formatting
black flower_fl/           # Python
```

> There is no `requirements-dev.txt` or `pytest` suite in this repo — the
> Python experiment drivers are run directly (see *Reproducing paper results*).
> Smart-contract behaviour is covered by `test/DAOJobCreation.ts`.

### Contribution Workflow

1. **Fork** the repository
2. **Create** feature branch: `git checkout -b feature/my-feature`
3. **Commit** changes: `git commit -am 'Add new feature'`
4. **Push** to branch: `git push origin feature/my-feature`
5. **Submit** Pull Request

### Areas for Contribution

- 🔧 **Optimizations**: Gas efficiency improvements
- 🧪 **Testing**: Expand test coverage
- 📚 **Documentation**: Tutorials, guides
- 🔒 **Security**: Audit smart contracts
- 🎨 **Visualization**: Enhanced plotting
- 🌐 **Integrations**: Support more FL frameworks
- 🔌 **Plugins**: Privacy-preserving techniques (DP, SMC)

---

## 📄 License

This project is licensed under the **MIT License** - see [LICENSE](LICENSE) file for details.
```
MIT License

Copyright (c) 2025 Luanmantegazine Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

[Full license text...]
```

---

## 🌐 Links

- **Repository**: [github.com/luanmantegazine/CryptoFL](https://github.com/luanmantegazine/CryptoFL)
- **Arbitrum Docs**: [docs.arbitrum.io](https://docs.arbitrum.io)
- **Flower Framework**: [flower.dev](https://flower.dev)
- **IPFS**: [ipfs.tech](https://ipfs.tech)
- **Hardhat**: [hardhat.org](https://hardhat.org)

---

## 📞 Contact

- **Project Lead**: [Your Name](mailto:your.email@university.edu)
- **Institution**: Your University
- **Lab**: Distributed Systems Lab

---

## 🙏 Acknowledgments

- **Flower Team** - Federated Learning framework
- **OpenZeppelin** - Secure smart contract libraries
- **Arbitrum Foundation** - Layer-2 scaling solution
- **Pinata** - IPFS pinning service
- **Research Advisors** - [Names]

---

<div align="center">

**Built with ❤️ for decentralized AI research**

⭐ Star this repo if you find it useful!

</div>
