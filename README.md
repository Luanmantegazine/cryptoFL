# Sample Hardhat 3 Beta Project (`node:test` and `viem`)

This project showcases a Hardhat 3 Beta project using the native Node.js test runner (`node:test`) and the `viem` library for Ethereum interactions.

To learn more about the Hardhat 3 Beta, please visit the [Getting Started guide](https://hardhat.org/docs/getting-started#getting-started-with-hardhat-3). To share your feedback, join our [Hardhat 3 Beta](https://hardhat.org/hardhat3-beta-telegram-group) Telegram group or [open an issue](https://github.com/NomicFoundation/hardhat/issues/new) in our GitHub issue tracker.

## Project Overview

This example project includes:

- A simple Hardhat configuration file.
- Foundry-compatible Solidity unit tests.
- TypeScript integration tests using [`node:test`](nodejs.org/api/test.html), the new Node.js native test runner, and [`viem`](https://viem.sh/).
- Examples demonstrating how to connect to different types of networks, including locally simulating OP mainnet.

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
