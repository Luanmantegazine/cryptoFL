import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { network } from "hardhat";
import { decodeEventLog, keccak256, stringToBytes } from "viem";

describe("DAO job creation", async function () {
  const connection = await network.connect();
  const { viem } = connection;
  const publicClient = await viem.getPublicClient();
  const [deployer, requester, trainer] = await viem.getWalletClients();

  if (!deployer || !requester || !trainer) {
    throw new Error("wallet clients not available");
  }

  const dao = await viem.deployContract("contracts/DAO.sol:DAO", {
    client: { wallet: deployer },
  });

  const daoAsRequester = await viem.getContractAt(
    "contracts/DAO.sol:DAO",
    dao.address,
    { client: { wallet: requester } },
  );

  const daoAsTrainer = await viem.getContractAt(
    "contracts/DAO.sol:DAO",
    dao.address,
    { client: { wallet: trainer } },
  );

  const spec = ["Proc", "16GB", "8 cores"] as const;

  const registerTrainerSimulation = await daoAsTrainer.simulate.registerTrainer([
    "Trainer description",
    spec,
  ]);

  await daoAsTrainer.write.registerTrainer(registerTrainerSimulation.request);

  await daoAsRequester.write.registerRequester();

  const trainerContractAddress = registerTrainerSimulation.result;

  const modelHash = keccak256(stringToBytes("model"));
  const endpointHash = keccak256(stringToBytes("endpoint"));

  const offerSimulation = await daoAsRequester.simulate.MakeOffer([
    "Job description",
    modelHash,
    endpointHash,
    "0x",
    1n,
    3n,
    trainerContractAddress,
  ]);

  await daoAsRequester.write.MakeOffer(offerSimulation.request);

  const pendingOffers = await daoAsTrainer.read.getPendingOffers();
  assert.equal(pendingOffers.length, 1);

  const offerId = pendingOffers[0];

  const acceptHash = await daoAsTrainer.write.AcceptOffer([offerId]);
  const acceptReceipt = await publicClient.waitForTransactionReceipt({ hash: acceptHash });

  assert.ok(acceptReceipt.logs.length > 0);

  const event = decodeEventLog({
    abi: dao.abi,
    data: acceptReceipt.logs[0].data,
    topics: acceptReceipt.logs[0].topics,
  });

  assert.equal(event.eventName, "JobContractCreated");

  const jobAddress = event.args?.job;
  assert.ok(typeof jobAddress === "string" && jobAddress !== "0x0000000000000000000000000000000000000000");
  assert.equal(event.args?.trainer, trainer.account.address);

  const isJob = await dao.read.isJob([jobAddress as `0x${string}`]);
  assert.equal(isJob, true);
});
