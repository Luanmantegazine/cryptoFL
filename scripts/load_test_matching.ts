/**
 * scripts/load_test_matching.ts — Stress-test do `matchTrainers` do contrato DAO.
 *
 * Faz deploy de um DAO novo na rede `localhost` (Hardhat node), registra N
 * trainers sintéticos progressivamente em thresholds (10, 50, 100, 500, …)
 * e mede para cada threshold:
 *   - wall clock de `matchTrainers` (view function, via `readContract`)
 *   - gas estimado da mesma chamada (via `estimateContractGas`).
 *
 * Uso:
 *   npx hardhat run scripts/load_test_matching.ts --network localhost          # default N=100
 *   npx hardhat run scripts/load_test_matching.ts --network localhost 500      # N=500
 *
 * Resultados salvos em `results/matching_load_test.json`.
 *
 * Observações:
 *   - Cada trainer precisa ser um endereço distinto (o DAO usa msg.sender e
 *     bloqueia re-registro). O script gera contas aleatórias com
 *     `generatePrivateKey()` e as financia a partir do funder principal.
 *   - Para N grande (≥ 500) o tempo total domina o funding/registro; a
 *     medição de matchTrainers em si fica rápida (é uma view).
 */
/// <reference types="hardhat/types" />
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { network } from "hardhat";
import { createWalletClient, http, parseEther } from "viem";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { hardhat as hardhatChain } from "viem/chains";

const RPC_URL = process.env.LOCAL_RPC_URL ?? "http://127.0.0.1:8545";
// Hardhat 3 runs scripts via the `run` task and does not forward positional
// args (process.argv[2] is "run"), so prefer the LOAD_TEST_N env var.
const N_RAW = process.env.LOAD_TEST_N ?? process.argv[2] ?? "100";
const N_MAX = parseInt(N_RAW, 10);
const DEFAULT_THRESHOLDS = [10, 50, 100, 500];

type Measurement = {
  n_trainers: number;
  time_ms: number;
  gas_estimated: string;
  matched_count: number;
};

function buildThresholds(nMax: number): number[] {
  const set = new Set<number>();
  for (const t of DEFAULT_THRESHOLDS) {
    if (t <= nMax) set.add(t);
  }
  set.add(nMax);
  return Array.from(set).sort((a, b) => a - b);
}

async function main(): Promise<void> {
  if (!Number.isFinite(N_MAX) || N_MAX <= 0) {
    throw new Error(`Argumento N inválido: '${process.argv[2]}'`);
  }

  const connection = await network.connect();
  const { viem } = connection;
  const publicClient = await viem.getPublicClient();
  const [funder] = await viem.getWalletClients();
  if (!funder) {
    throw new Error("Nenhuma carteira disponível na rede. Verifique a configuração.");
  }

  // Carrega ABI do artefato compilado (não tenta tipos gerados).
  const artifactPath = resolve("artifacts/contracts/DAO.sol/DAO.json");
  const daoArtifact = JSON.parse(readFileSync(artifactPath, "utf-8"));
  const daoAbi = daoArtifact.abi as unknown[];

  console.log(`Deploying DAO (funder=${funder.account.address})...`);
  const dao = await viem.deployContract("contracts/DAO.sol:DAO", []);
  const daoAddress = dao.address as `0x${string}`;
  console.log(`DAO deployed at ${daoAddress}`);

  const thresholds = buildThresholds(N_MAX);
  console.log(`Thresholds: ${thresholds.join(", ")}  (N_MAX=${N_MAX})`);

  const requirements = {
    description: "",
    valueByUpdate: 0n,
    minRating: 0n,
    tags: [] as string[],
    canditatesToReturn: 5n,
  };

  const measurements: Measurement[] = [];
  let registered = 0;

  for (const target of thresholds) {
    while (registered < target) {
      const pk = generatePrivateKey();
      const acc = privateKeyToAccount(pk);

      // Funda a conta com ETH suficiente para 1 tx de registro.
      const fundHash = await funder.sendTransaction({
        to: acc.address,
        value: parseEther("0.05"),
      });
      await publicClient.waitForTransactionReceipt({ hash: fundHash });

      const trainerClient = createWalletClient({
        account: acc,
        chain: hardhatChain,
        transport: http(RPC_URL),
      });

      const txHash = await trainerClient.writeContract({
        address: daoAddress,
        abi: daoAbi as never,
        functionName: "registerTrainer",
        args: [
          `Trainer sintético ${registered}`,
          {
            processor: `CPU-${registered}`,
            ram: "16GB",
            cpu: "8 cores",
          },
        ],
      });
      await publicClient.waitForTransactionReceipt({ hash: txHash });
      registered++;

      if (registered % 25 === 0) {
        console.log(`  ... ${registered} trainers registrados`);
      }
    }

    // Mede matchTrainers (view).
    const tStart = performance.now();
    const matched = (await publicClient.readContract({
      address: daoAddress,
      abi: daoAbi as never,
      functionName: "matchTrainers",
      args: [requirements],
    })) as readonly `0x${string}`[];
    const elapsedMs = performance.now() - tStart;

    const gas = await publicClient.estimateContractGas({
      account: funder.account.address,
      address: daoAddress,
      abi: daoAbi as never,
      functionName: "matchTrainers",
      args: [requirements],
    });

    const m: Measurement = {
      n_trainers: target,
      time_ms: Number(elapsedMs.toFixed(3)),
      gas_estimated: gas.toString(),
      matched_count: matched.length,
    };
    measurements.push(m);
    console.log(`N=${target}  time=${m.time_ms}ms  gas=${m.gas_estimated}  matched=${m.matched_count}`);
  }

  // Tabela final
  console.log("\nN trainers | tempo (ms) | gas estimado");
  console.log("-----------|------------|-------------");
  for (const r of measurements) {
    console.log(
      `${String(r.n_trainers).padEnd(11)}| ${String(r.time_ms).padEnd(11)}| ${r.gas_estimated}`,
    );
  }

  mkdirSync(resolve("results"), { recursive: true });
  const outPath = resolve("results/matching_load_test.json");
  writeFileSync(
    outPath,
    JSON.stringify(
      {
        dao_address: daoAddress,
        n_max: N_MAX,
        thresholds,
        measurements,
        funder: funder.account.address,
        timestamp: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
  console.log(`\nResultados salvos em ${outPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
