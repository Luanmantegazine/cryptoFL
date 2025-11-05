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

  console.log("Deploying DAO with account:", wallet.account.address);

  const txHash = await viem.deployContract("DAO", []);
  console.log("Awaiting deployment tx:", txHash);

  const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });

  if (!receipt.contractAddress) {
    throw new Error("Não foi possível obter o endereço do contrato DAO");
  }

  const chain = await publicClient.getChainId();

  console.log("DAO deployed at:", receipt.contractAddress);
  console.log("Chain id:", chain);

  const outDir = resolve("deployments");
  mkdirSync(outDir, { recursive: true });
  const filePath = join(outDir, `dao-${chain}.json`);

  const payload = {
    dao: receipt.contractAddress,
    chainId: Number(chain),
    network: network.name,
    deployer: wallet.account.address,
    transactionHash: txHash,
    timestamp: new Date().toISOString(),
  };

  writeFileSync(filePath, JSON.stringify(payload, null, 2), { encoding: "utf-8" });
  console.log(format("Saved deployment info to %s", filePath));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});

