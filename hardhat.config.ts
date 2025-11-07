import hardhatToolboxViemPlugin from "@nomicfoundation/hardhat-toolbox-viem";
import { configVariable, defineConfig } from "hardhat/config";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function loadEnvFile(file = ".env") {
  const fullPath = resolve(process.cwd(), file);
  if (!existsSync(fullPath)) {
    return;
  }

  const content = readFileSync(fullPath, "utf8");
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const eqIndex = line.indexOf("=");
    if (eqIndex === -1) {
      continue;
    }

    const key = line.slice(0, eqIndex).trim();
    if (!key || process.env[key] !== undefined) {
      continue;
    }

    const value = line.slice(eqIndex + 1).trim().replace(/^['"]|['"]$/g, "");
    process.env[key] = value;
  }
}

loadEnvFile();

export default defineConfig({
  plugins: [hardhatToolboxViemPlugin],
  solidity: {
    profiles: {
      default: {
        version: "0.8.28",
        settings: {
          optimizer: {
            enabled: true,
            runs: 1000,
          },
        },
      },
      production: {
        version: "0.8.28",
        settings: {
          optimizer: {
            enabled: true,
            runs: 1000,
          },
        },
      },
    },
  },
  networks: {
    hardhatMainnet: {
      type: "edr-simulated",
      chainType: "l1",
    },
    hardhatOp: {
      type: "edr-simulated",
      chainType: "op",
    },
    sepolia: {
      type: "http",
      chainType: "l1",
      url: configVariable("SEPOLIA_RPC_URL"),
      accounts: [configVariable("SEPOLIA_PRIVATE_KEY")],
    },
    optimism: {
      type: "http",
      chainType: "op",
      url: configVariable("OPTIMISM_RPC_URL"),
      accounts: [configVariable("OPTIMISM_PRIVATE_KEY")],
    },
    arbitrum: {
      type: "http",
      chainType: "generic",
      url: configVariable("ARBITRUM_RPC_URL"),
      accounts: [configVariable("ARBITRUM_PRIVATE_KEY")],
    },
    base: {
      type: "http",
      chainType: "generic",
      url: configVariable("BASE_RPC_URL"),
      accounts: [configVariable("BASE_PRIVATE_KEY")],
    },
    arbitrumSepolia: {
      type: "http",
      chainType: "generic", // ou "op" se for L2 estilo Optimism
      url: configVariable("RPC_URL"), // Lê o RPC_URL do seu .env
      accounts: [configVariable("PRIVATE_KEY")], // Lê o PRIVATE_KEY do seu .env
    },
    localhost: {
      type: "http",
      chainType: "l1",
      url: "http://127.0.0.1:8545",
      accounts: [configVariable("PRIVATE_KEY")], // Vai ler a chave que você acabou de colocar no .env
    },

  },
});
