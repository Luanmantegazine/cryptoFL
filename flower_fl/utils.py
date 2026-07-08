import os, numpy as np
from dotenv import load_dotenv
load_dotenv()

ROUNDS = int(os.getenv("ROUNDS", "3"))


def _flag(name: str, default: bool) -> bool:
    """Lê uma flag booleana do ambiente (1/true/yes/on). Ausente -> default."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# Camadas de descentralização (desacopladas — ver ablação):
#   USE_IPFS    -> armazenar os pesos no IPFS e usar o CID retornado.
#   USE_ONCHAIN -> ancorar o CID (ou um hash de conteúdo) on-chain.
# São INDEPENDENTES: o modo `no_ipfs` da ablação usa USE_IPFS=false +
# USE_ONCHAIN=true (ancora um hash de conteúdo, sem IPFS).
#
# Retrocompatibilidade: `SKIP_IPFS=true` (flag antiga) mapeia para
# USE_IPFS=false, mas NÃO força USE_ONCHAIN=false — antes ela desligava
# as duas camadas de uma vez, o que colapsava `no_ipfs` em `baseline`.
# ------------------------------------------------------------------
_SKIP_IPFS = _flag("SKIP_IPFS", False)
USE_IPFS = _flag("USE_IPFS", default=not _SKIP_IPFS)
USE_ONCHAIN = _flag("USE_ONCHAIN", default=True)


def set_seed(seed: int) -> None:
    """Fixa as sementes de random/numpy/torch para reprodutibilidade por-rep."""
    import random as _random
    _random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def init_weights() -> list[np.ndarray]:
    # Modelo mínimo (demonstração) — troque por pesos reais (Keras/PyTorch → np)
    return [np.zeros((32, 32)), np.zeros((32,)), np.zeros((10, 32))]
