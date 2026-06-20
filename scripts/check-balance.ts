/**
 * scripts/check-balance.ts — Print the signer address, chain id and ETH balance
 * for the selected network. Use this before deploying to Arbitrum Sepolia to
 * confirm the account read from PRIVATE_KEY/RPC_URL is funded.
 *
 * Usage:
 *   npx hardhat run scripts/check-balance.ts --network localhost
 *   npx hardhat run scripts/check-balance.ts --network arbitrumSepolia
 */
import { network } from "hardhat";
import { formatEther } from "viem";

async function main(): Promise<void> {
  const connection = await network.connect();
  const { viem } = connection;

  const publicClient = await viem.getPublicClient();
  const [wallet] = await viem.getWalletClients();

  const chainId = await publicClient.getChainId();
  console.log(`Network : ${connection.networkName}`);
  console.log(`Chain id: ${chainId}`);

  if (!wallet) {
    console.log(
      "No wallet configured for this network. Set PRIVATE_KEY (and RPC_URL) " +
        "in .env for the chosen network.",
    );
    return;
  }

  const address = wallet.account.address;
  const balanceWei = await publicClient.getBalance({ address });
  console.log(`Signer  : ${address}`);
  console.log(`Balance : ${formatEther(balanceWei)} ETH`);

  if (balanceWei === 0n) {
    console.log(
      "\n⚠ Balance is 0. Fund this address before deploying. For Arbitrum " +
        "Sepolia use a faucet, e.g. https://faucet.quicknode.com/arbitrum/sepolia",
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
