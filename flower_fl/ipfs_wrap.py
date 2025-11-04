import os, time, json, tempfile, pathlib, requests
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv()

PINATA_JWT = os.getenv("PINATA_JWT")
PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_GATEWAY = os.getenv("PINATA_GATEWAY", "https://gateway.pinata.cloud/ipfs/")

def ipfs_add_bytes(data: bytes, filename: str= 'blob.bib') -> str:
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    with tempfile.NamedTemporaryFile(delete=False) as tmp
        tmp.write(data)
        tmp.flush()
        files = {"file": (filename, open(tmp.name, "rb"))}
        r = requests.post(PINATA_PIN_URL, files=files, headers=headers, timeout=60)
        r.raise_for_status()
        cid = r.json()["IpfsHash"]
        return cid

def ipfs_add_numpy_arrays(arrays: List, filename="weights.npz") -> str:
    import numpy as np
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        np.savez(tmp.name, *arrays)
        tmp.flush()
        with open(tmp.name, "rb") as f:
            return ipfs_add_bytes(f.read(), filename=filename)

def ipfs_get_npz(cid: str) -> Tuple[List, str]:
    import numpy as np
    url = f"{PINATA_GATEWAY}{cid}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".npz") as tmp:
        tmp.write(r.content)
        tmp.flush()
        npz = np.load(tmp.name, allow_pickle=False)
        arrays = [npz[k] for k in npz.files]
        return arrays, tmp.name