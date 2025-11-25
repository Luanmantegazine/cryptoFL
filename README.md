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

**CryptoFL** is a research platform that integrates **Federated Learning** (FL) with **blockchain technology** to create a trustless, transparent, and economically viable marketplace for distributed machine learning tasks.

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

Create `.env` file in project root:
```bash
# Blockchain Configuration
RPC_URL=http://127.0.0.1:8545
PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# Contract ABIs
DAO_ABI_PATH=artifacts/contracts/DAO.sol/DAO.json
JOB_ABI_PATH=artifacts/contracts/JobContract.sol/JobContract.json

# IPFS Configuration
PINATA_JWT=your_pinata_jwt_token_here
PINATA_GATEWAY=https://gateway.pinata.cloud/ipfs/

# Experiment Configuration
ROUNDS=3
MIN_CLIENTS=3
SAVE_METRICS=true
METRICS_FILE=results/server_metrics.json

# Deployment Directories
DEPLOYMENTS_DIR=deployments
IGNITION_DIR=ignition/deployments
```

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
python3 -m flower_fl.deploy-job
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

## 📁 Project Structure
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
│   ├── deploy-job.py          # Setup automation
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

## 📊 Evaluation & Results

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
# Install dev dependencies
pip install -r requirements-dev.txt
npm install --include=dev

# Run tests
npm test                    # Smart contract tests
pytest tests/               # Python tests (if available)

# Lint code
npm run lint               # Solidity
black flower_fl/           # Python
```

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

Copyright (c) 2025 CryptoFL Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

[Full license text...]
```

---

## 📖 Citation

If you use this project in your research, please cite:
```bibtex
@article{cryptofl2025,
  title={A Blockchain-Based Platform for Federated Learning},
  author={Lastname, Firstname and Lastname, Firstname},
  journal={Journal Not Specified},
  year={2025},
  url={https://github.com/your-username/CryptoFL}
}
```

---

## 🌐 Links

- **Research Paper**: [Blockchain_FL_Paper.pdf](Blockchain_FL_Paper.pdf)
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
