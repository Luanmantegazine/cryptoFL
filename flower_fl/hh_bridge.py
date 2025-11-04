import os, subprocess, json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

NODE_BIN = os.getenv("NODE_BIN", "node")
HARDHAT_DIR = os.getenv("HARDHAT_DIR", os.path.join(os.path.dirname(__file__), "..", "hardhat_bridge"))


def _run_node(script: str, args: list[str]) -> dict:
    cmd = [NODE_BIN, script] + args
    proc = subprocess.run(cmd, cwd=HARDHAT_DIR, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Node script failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"stdout": proc.stdout}


def update_global_model(job_id: int, cid: str):
    script = os.path.join("scripts", "updateGlobalModel.js")
    return _run_node(script, [str(job_id), cid])


def send_update(job_id: int, cid: str):
    script = os.path.join("scripts", "sendUpdate.js")
    return _run_node(script, [str(job_id), cid])
