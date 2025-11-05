import os, numpy as np
from dotenv import load_dotenv
load_dotenv()

JOB_ID = int(os.getenv("JOB_ID", "1"))
ROUNDS = int(os.getenv("ROUNDS", "3"))

def init_weights() -> list[np.ndarray]:
    # Modelo mínimo (demonstração) — troque por pesos reais (Keras/PyTorch → np)
    return [np.zeros((32, 32)), np.zeros((32,)), np.zeros((10, 32))]
