# Sample Hardhat 3 Beta Project (`node:test` and `viem`)

This project showcases a Hardhat 3 Beta project using the native Node.js test runner (`node:test`) and the `viem` library for Ethereum interactions.

To learn more about the Hardhat 3 Beta, please visit the [Getting Started guide](https://hardhat.org/docs/getting-started#getting-started-with-hardhat-3). To share your feedback, join our [Hardhat 3 Beta](https://hardhat.org/hardhat3-beta-telegram-group) Telegram group or [open an issue](https://github.com/NomicFoundation/hardhat/issues/new) in our GitHub issue tracker.

## Project Overview

This example project includes:

- A simple Hardhat configuration file.
- Foundry-compatible Solidity unit tests.
- TypeScript integration tests using [`node:test`](nodejs.org/api/test.html), the new Node.js native test runner, and [`viem`](https://viem.sh/).
- Examples demonstrating how to connect to different types of networks, including locally simulating OP mainnet.

### Negotiation and training workflow

The DAO, profile contracts, and the Flower/IPFS tooling now expose a full end-to-end cycle that emphasises transparency and privacy:

- **Profile & pricing controls:** trainers keep their hardware specification, optional tags, and a self-declared `pricePerUpdate`. The DAO rejects offers that pay below the advertised amount and filters matches by budget and minimum reputation. Trainers and requesters can update tags/pricing directly on their dedicated profile contracts (ownership restricted).
- **Escrowed updates with approvals:** trainers (or the requester) may submit encrypted IPFS hashes through `recordClientUpdate`. Each submission is tracked as a pending update. The requester must confirm delivery with `approveClientUpdate`, which increases the releasable escrow balance. Funds are still withdrawn through `releaseJobPayment`, keeping the DAO as the single escrow authority.
- **Auditable model history:** every aggregated global model pushed by the Flower server calls `publishGlobalModel`, which now stores a timestamped log retrievable on-chain (`globalModelHistoryLength` + `getGlobalModel`). This removes the need to rely solely on event logs for historical verification.
- **Reputation loop:** once a job is fulfilled, the requester and the trainer can rate each other via `rateTrainer` and `rateRequester`. Ratings stay within the contract, producing an average score (0–10) that future matches consume. Evaluations are stored with optional comments for off-chain indexers.
- **Off-chain helpers:** Python utilities (`flower_fl/onchain_dao.py`) include helpers for approving updates and submitting ratings so automation scripts can react to Flower callbacks.

## Usage

### Deploying and retrieving the DAO address

Use the provided Hardhat script to deploy the `DAO` contract on the network of your choice. The script prints the address and saves a JSON file under `deployments/dao-<chainId>.json`, which is automatically consumed by the Python helpers when `DAO_ADDRESS` is left unset or configured as `0x000…0000`.

```shell
npx hardhat run --network arbitrumSepolia scripts/deploy-dao.ts
```

After the transaction is mined the output will resemble:

```
DAO deployed at: 0x1234...abcd
Saved deployment info to deployments/dao-421614.json
```

Update your `.env` with the ABI path only:

```
DAO_ABI_PATH=artifacts/contracts/DAO.sol/DAO.json
```

When `DAO_ADDRESS` is omitted or set to the zero address, the Python modules (`flower_fl/onchain.py` and `flower_fl/onchain_dao.py`) will load the value stored in `deployments/` or the latest Ignition deployment (e.g. `ignition/deployments/chain-421614/*/deployed_addresses.json`).

If you already deployed using Hardhat Ignition, you can skip the script—the helpers will detect the recorded address automatically.

#### Passo a passo (PT-BR)

1. **Configurar variáveis da rede**: defina `RPC_URL`/`<NETWORK>_RPC_URL` e a `PRIVATE_KEY` (ou use o keystore do Hardhat) para a rede onde deseja publicar o contrato.
2. **Executar o script de deploy**: rode `npx hardhat run --network <suaRede> scripts/deploy-dao.ts`. O terminal exibirá o endereço implantado (`DAO deployed at: ...`).
3. **Confirmar o arquivo salvo**: o script grava `deployments/dao-<chainId>.json`. Confira com `cat deployments/dao-421614.json` (substitua pelo `chainId` da sua rede) para visualizar o endereço.
4. **Atualizar a `.env`**: copie o valor `dao` registrado no JSON e preencha `DAO_ADDRESS` se quiser fixar manualmente. Se preferir, deixe `DAO_ADDRESS=0x0000000000000000000000000000000000000000` ou remova a linha; os módulos Python localizarão automaticamente o endereço usando `deployments/` ou o histórico do Hardhat Ignition.
5. **Reutilizar em outros ambientes**: compartilhe o arquivo `deployments/dao-<chainId>.json` com outros serviços (por exemplo, a aplicação Python/Flower) para que todos os componentes usem o mesmo endereço sem necessidade de redeploy.

> 💡 **Dica:** a configuração do Hardhat já ativa o otimizador do compilador (`runs: 200`). Se você vinha utilizando artefatos antigos (com instruções de `console.log` ou sem otimização) limpe os diretórios `artifacts/` e `cache/` ou execute `npx hardhat clean` antes de recompilar para evitar o erro `trying to deploy a contract whose code is too large`.

#### Usando a rede local Hardhat (`localhost`)

1. Em um terminal, inicialize um nó local: `npx hardhat node`. Esse comando expõe RPC em `http://127.0.0.1:8545` e disponibiliza contas pré-carregadas (as mesmas listadas no console do Hardhat).
2. Em outro terminal, exporte as variáveis de ambiente (`RPC_URL=http://127.0.0.1:8545` e uma `PRIVATE_KEY` das fornecidas pelo nó) e execute `npx hardhat run --network localhost scripts/deploy-dao.ts`.
3. O script criará `deployments/dao-31337.json` (31337 é o `chainId` padrão da rede local). Use `cat deployments/dao-31337.json` para ver o endereço salvo e, se desejar, copie-o para `DAO_ADDRESS` no `.env`.
4. Com `DAO_ADDRESS` zerado, os scripts Python carregarão automaticamente o valor de `deployments/dao-31337.json`, então não é obrigatório atualizar a variável.

### Running Tests

To run all the tests in the project, execute the following command:

```shell
npx hardhat test
```

You can also selectively run the Solidity or `node:test` tests:

```shell
npx hardhat test solidity
npx hardhat test nodejs
```

### Make a deployment to Sepolia

This project includes an example Ignition module to deploy the contract. You can deploy this module to a locally simulated chain or to Sepolia.

To run the deployment to a local chain:

```shell
npx hardhat ignition deploy ignition/modules/Counter.ts
```

To run the deployment to Sepolia, you need an account with funds to send the transaction. The provided Hardhat configuration includes a Configuration Variable called `SEPOLIA_PRIVATE_KEY`, which you can use to set the private key of the account you want to use.

You can set the `SEPOLIA_PRIVATE_KEY` variable using the `hardhat-keystore` plugin or by setting it as an environment variable.

To set the `SEPOLIA_PRIVATE_KEY` config variable using `hardhat-keystore`:

```shell
npx hardhat keystore set SEPOLIA_PRIVATE_KEY
```

After setting the variable, you can run the deployment with the Sepolia network:

```shell
npx hardhat ignition deploy --network sepolia ignition/modules/Counter.ts
```
