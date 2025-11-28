from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from web3 import Web3


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _extract_address(payload: dict, name: str) -> Optional[str]:
    keys = [
        name,
        name.lower(),
        name.upper(),
        "dao",
        "address",
    ]
    for key in keys:
        addr = payload.get(key)
        if isinstance(addr, str) and Web3.is_address(addr):
            return Web3.to_checksum_address(addr)

    contracts = payload.get("contracts")
    if isinstance(contracts, dict):
        for key in (name, name.lower(), name.upper()):
            entry = contracts.get(key)
            if isinstance(entry, dict):
                addr = entry.get("address") or entry.get("contractAddress")
                if isinstance(addr, str) and Web3.is_address(addr):
                    return Web3.to_checksum_address(addr)

    for value in payload.values():
        if isinstance(value, str) and Web3.is_address(value):
            return Web3.to_checksum_address(value)
    return None


def discover_contract_address(
    name: str,
    chain_id: int,
    *,
    deployments_dir: str | os.PathLike[str] = "deployments",
    ignition_dir: str | os.PathLike[str] = "ignition/deployments",
) -> Optional[str]:

    search_paths = []
    base = Path(deployments_dir)
    if base.exists():
        search_paths.extend(
            [
                base / f"{name}-{chain_id}.json",
                base / f"{name.lower()}-{chain_id}.json",
                base / f"{chain_id}-{name}.json",
                base / f"{chain_id}-{name.lower()}.json",
                base / f"{name}.json",
                base / f"{name.lower()}.json",
            ]
        )

    ignition_base = Path(ignition_dir) / f"chain-{chain_id}"
    if ignition_base.exists():
        search_paths.extend(sorted(ignition_base.rglob("deployed_addresses.json")))

    for path in search_paths:
        if not path.exists():
            continue
        payload = _read_json(path)
        if not payload:
            continue
        address = _extract_address(payload, name)
        if address:
            return address
    return None


def resolve_address(
    explicit: Optional[str],
    w3: Web3,
    *,
    name: str,
    deployments_dir: str | os.PathLike[str] = "deployments",
    ignition_dir: str | os.PathLike[str] = "ignition/deployments",
) -> str:

    if explicit and Web3.is_address(explicit) and not _is_zero(explicit):
        return Web3.to_checksum_address(explicit)

    chain_id = w3.eth.chain_id
    discovered = discover_contract_address(
        name,
        chain_id,
        deployments_dir=deployments_dir,
        ignition_dir=ignition_dir,
    )
    if discovered:
        return discovered

    raise RuntimeError(
        f"Não foi possível descobrir o endereço do contrato {name}. "
        "Informe DAO_ADDRESS no .env ou execute scripts/deploy-dao.ts."
    )


def _is_zero(address: str) -> bool:
    return int(address, 16) == 0

