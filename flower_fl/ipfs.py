import os, tempfile, requests
from typing import List, Tuple
import numpy as np
from dotenv import load_dotenv

load_dotenv()

PINATA_JWT = os.getenv("PINATA_JWT")
PINATA_GATEWAY = os.getenv("PINATA_GATEWAY", "https://gateway.pinata.cloud/ipfs/")
PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"

def ipfs_add_numpy(arrays: List[np.ndarray], filename="weights.npz") -> str:
    assert PINATA_JWT, "PINATA_JWT não configurado"
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        np.savez(tmp.name, *arrays)
        tmp.flush()
        with open(tmp.name, "rb") as f:
            files = {"file": (filename, f)}
            r = requests.post(PIN_URL, headers=headers, files=files, timeout=60)
            r.raise_for_status()
            return r.json()["IpfsHash"]

def ipfs_get_numpy(cid: str) -> List[np.ndarray]:
    url = f"{PINATA_GATEWAY}{cid}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        tmp.write(r.content); tmp.flush()
        data = np.load(tmp.name, allow_pickle=False)
        return [data[k] for k in data.files]
