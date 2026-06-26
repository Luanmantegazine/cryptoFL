# CryptoFL — Architecture Diagram

Diagrama de arquitetura do **CryptoFL**, plataforma de Federated Learning coordenada por
contratos inteligentes (DAO marketplace) com armazenamento em IPFS e liquidação em Layer-2/Layer-1.

> Repositório: https://github.com/Luanmantegazine/cryptoFL

## Diagrama principal (componentes e fluxo)

```mermaid
flowchart TB
    subgraph Actors["👥 Participantes"]
        REQ["Requester<br/>(Client)"]
        TRN["Trainer<br/>(Worker)"]
    end

    subgraph Onchain["⛓️ Camada On-Chain (Smart Contracts — Solidity)"]
        direction TB
        DAO["DAO.sol<br/>Registro & Matching<br/>de participantes"]
        JOB["JobContract.sol<br/>Escrow + registro de CIDs<br/>(1 por tarefa)"]
        RPROXY["Requester.sol<br/>(Proxy)"]
        TPROXY["Trainer.sol<br/>(Proxy)"]
        DAO -->|cria| JOB
    end

    subgraph FL["🌸 Camada de Federated Learning (Flower — off-chain)"]
        direction TB
        SRV["FL Server<br/>BlockchainFLStrategy<br/>(FedAvg + MetricsCollector)"]
        C1["Client 1"]
        C2["Client 2"]
        CN["Client N"]
        SRV <-->|configure_fit / aggregate_fit| C1
        SRV <--> C2
        SRV <--> CN
    end

    subgraph Storage["📦 Armazenamento descentralizado"]
        IPFS["IPFS / Pinata<br/>Pesos do modelo<br/>CID: bafybei..."]
    end

    subgraph Settlement["🏛️ Liquidação & Segurança"]
        L2["Arbitrum L2 (Sepolia)<br/>Transações de baixo custo"]
        L1["Ethereum L1 (Mainnet)<br/>Liquidação final"]
    end

    %% Fluxo de atores
    REQ -->|registra / cria oferta| DAO
    TRN -->|registra / aceita| DAO
    TRN -->|assina| JOB
    REQ -->|deposita escrow| JOB
    REQ -.->|representado por| RPROXY
    TRN -.->|representado por| TPROXY

    %% Fluxo FL <-> blockchain
    TRN -->|executa FL| SRV
    SRV -->|publica modelo global| IPFS
    C1 -->|envia update| IPFS
    IPFS -->|download por CID| SRV
    SRV -->|registra CID + libera pagamento| JOB

    %% Liquidação
    JOB --> L2
    L2 -->|batched & rolled up| L1

    classDef chain fill:#f5e6ff,stroke:#7d3cff,color:#1a1a1a;
    classDef fl fill:#e6f7e6,stroke:#2e9e2e,color:#1a1a1a;
    classDef store fill:#fff3e0,stroke:#e6850e,color:#1a1a1a;
    classDef actor fill:#e3f0ff,stroke:#1f6feb,color:#1a1a1a;
    class DAO,JOB,RPROXY,TPROXY,L1,L2 chain;
    class SRV,C1,C2,CN fl;
    class IPFS store;
    class REQ,TRN actor;
```

## Diagrama de sequência (ciclo de vida de uma tarefa)

```mermaid
sequenceDiagram
    autonumber
    participant R as Requester
    participant D as DAO.sol
    participant J as JobContract
    participant T as Trainer
    participant S as FL Server (Flower)
    participant C as FL Clients
    participant I as IPFS (Pinata)

    Note over R,T: Fase 1 — Setup (On-Chain)
    R->>D: register() / createOffer()
    T->>D: register()
    R->>D: matchTrainers(requisitos)
    T->>J: aceita oferta → deploy JobContract
    R->>J: assina + deposita escrow
    T->>J: assina

    Note over S,I: Fase 2 — Treino (Híbrido, off-chain + on-chain)
    S->>I: publica modelo inicial
    I-->>S: CID
    S->>J: registra CID inicial
    loop A cada round até numberOfUpdates
        C->>I: download modelo (via CID)
        C->>C: treino local (dados privados)
        C->>I: upload do update
        I-->>S: CIDs dos updates
        S->>S: FedAvg (agregação)
        S->>I: publica modelo global
        S->>J: registra CID + libera valueByUpdate
    end
    J-->>R: Status: Fulfilled (escrow liquidado)
```
