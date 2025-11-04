// @ts-ignore
import { ethers } from "hardhat";
import * as fs from "fs";
import * as dotenv from "dotenv";
dotenv.config();

async function main() {
  const [jobIdStr, cid] = process.argv.slice(2);
  if (!jobIdStr || !cid) throw new Error("usage: sendUpdate <jobId> <cid>");
  const jobId = BigInt(jobIdStr);

  const provider = new ethers.JsonRpcProvider(process.env.RPC_URL_ARBITRUM);
  const wallet = new ethers.Wallet(process.env.PRIVATE_KEY!, provider);

  const abiPath = process.env.DAO_ABI_PATH!;
  const abi = JSON.parse(fs.readFileSync(abiPath, "utf8")).abi;
  const dao = new ethers.Contract(process.env.DAO_ADDRESS!, abi, wallet);

  // ajuste o nome exatamente como está no seu contrato:
  const tx = await dao.SendUpdate(cid, jobId);
  const rec = await tx.wait();
  console.log(JSON.stringify({ txHash: rec?.hash || tx.hash, jobId: jobId.toString(), cid }));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
