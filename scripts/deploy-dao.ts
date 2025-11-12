import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { format } from "node:util";
import { network } from "hardhat";

async function main() {
  const connection = await network.connect();
  const { viem } = connection;

  const publicClient = await viem.getPublicClient();
  const [wallet] = await viem.getWalletClients();

  if (!wallet) {
    throw new Error("Nenhuma carteira configurada. Defina PRIVATE_KEY na rede escolhida.");
  }

  // Deploy do DAO (Sem bibliotecas)
  console.log("Deploying DAO with account:", wallet.account.address);

  const daoContract = await viem.deployContract("contracts/DAO.sol:DAO", []);

  console.log("Deployment finished.");

  const contractAddress = daoContract.address;
  const transactionHash = daoContract.deploymentTransaction?.hash; // Usamos ?.hash

  if (!contractAddress) {
    throw new Error("Não foi possível obter o endereço do contrato DAO");
  }

  const chain = await publicClient.getChainId();

  console.log("DAO deployed at:", contractAddress);
  console.log("Chain id:", chain);

  const outDir = resolve("deployments");
  mkdirSync(outDir, { recursive: true });
  const filePath = join(outDir, `dao-${chain}.json`);

  const payload = {
    dao: contractAddress,
    chainId: Number(chain),
    network: connection.networkName,
    deployer: wallet.account.address,
    transactionHash: transactionHash ?? "N/A",
    timestamp: new Date().toISOString(),
  };

  writeFileSync(filePath, JSON.stringify(payload, null, 2), { encoding: "utf-8" });
  console.log(format("Saved deployment info to %s", filePath));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});