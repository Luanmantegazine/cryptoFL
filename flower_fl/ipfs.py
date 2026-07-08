import os, tempfile, requests
from typing import List
import numpy as np
from dotenv import load_dotenv

load_dotenv()

PINATA_JWT = os.getenv("PINATA_JWT")
PINATA_GATEWAY = os.getenv("PINATA_GATEWAY", "https://gateway.pinata.cloud/ipfs/")
PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
IPFS_API_URL = os.getenv("IPFS_API_URL")
IPFS_GATEWAYS = [g.strip() for g in os.getenv("IPFS_GATEWAYS", "").split(",") if g.strip()]


def _pinata_add(path: str, filename: str) -> str:
    assert PINATA_JWT, "PINATA_JWT não configurado"
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    with open(path, "rb") as f:
        files = {"file": (filename, f)}
        r = requests.post(PIN_URL, headers=headers, files=files, timeout=60)
        r.raise_for_status()
        return r.json()["IpfsHash"]


def _local_add(path: str) -> str:
    assert IPFS_API_URL, "Configure PINATA_JWT ou IPFS_API_URL"
    url = f"{IPFS_API_URL.rstrip('/')}/api/v0/add"
    with open(path, "rb") as f:
        files = {"file": (os.path.basename(path), f)}
        r = requests.post(url, files=files, timeout=60)
        r.raise_for_status()
        return r.json()["Hash"]


def ipfs_add_numpy(arrays: List[np.ndarray], filename="weights.npz") -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        np.savez(tmp.name, *arrays)
        tmp.flush()
        if PINATA_JWT:
            return _pinata_add(tmp.name, filename)
        return _local_add(tmp.name)


def content_hash_numpy(arrays: List[np.ndarray]) -> str:
    """Hash de conteúdo determinístico dos pesos serializados (sem IPFS).

    Usado no modo `no_ipfs` da ablação: os pesos trafegam pelo protocolo
    Flower (não pelo IPFS), mas ainda precisamos de uma referência de
    conteúdo estável para ancorar on-chain. Retorna ``"sha256:<hex>"``.

    Não usa ``np.savez`` (cujos metadados de zip não são determinísticos);
    faz o hash de dtype+shape+bytes contíguos de cada array, na ordem.
    """
    import hashlib
    h = hashlib.sha256()
    for arr in arrays:
        a = np.ascontiguousarray(arr)
        h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return "sha256:" + h.hexdigest()


def _download_from_gateway(cid: str) -> bytes:
    gateways = IPFS_GATEWAYS or [PINATA_GATEWAY]
    for gateway in gateways:
        url = f"{gateway.rstrip('/')}/{cid}" if not gateway.endswith("/") else f"{gateway}{cid}"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            continue
    raise RuntimeError(f"Falha ao baixar CID {cid} em gateways configurados")


def ipfs_get_numpy(cid: str) -> List[np.ndarray]:
    raw = _download_from_gateway(cid)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        tmp.write(raw)
        tmp.flush()
        data = np.load(tmp.name, allow_pickle=False)
        return [data[k] for k in data.files]
