"""Corrige o flwr 1.7.0 para importar sob NumPy 2.x.

O flwr 1.7.0 usa ``np.float_`` (e afins), que foram **removidos no NumPy 2.0**.
No Colab/GPU o torch/torchvision exigem NumPy 2.x, então não dá para rebaixar o
NumPy — em vez disso trocamos os aliases removidos pelos nomes válidos. É uma
edição mínima e não muda a semântica do treino (verificado: acc idêntica).

Uso:
    python scripts/patch_flwr_numpy2.py

Idempotente: rodar de novo não causa dano. Localiza o flwr sem importá-lo
(``importlib.util.find_spec``), porque com NumPy 2.x o import quebraria aqui.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

# Aliases removidos no NumPy 2.0 -> substitutos válidos.
REPLACEMENTS = {
    "np.float_": "np.float64",
    "np.complex_": "np.complex128",
    "np.unicode_": "np.str_",
    "np.object0": "np.object_",
    "np.int0": "np.intp",
    "np.uint0": "np.uintp",
    "np.bool8": "np.bool_",
}


def main() -> int:
    spec = importlib.util.find_spec("flwr")
    if spec is None or not spec.submodule_search_locations:
        print("ERRO: flwr não está instalado.", file=sys.stderr)
        return 1

    root = pathlib.Path(spec.submodule_search_locations[0])
    patched = 0
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = text
        for old, repl in REPLACEMENTS.items():
            new = new.replace(old, repl)
        if new != text:
            path.write_text(new, encoding="utf-8")
            patched += 1
            print(f"  patched: {path.relative_to(root.parent)}")

    print(f"OK: {patched} arquivo(s) ajustado(s) para NumPy 2.x"
          if patched else "OK: nada a corrigir (flwr já compatível com NumPy 2.x)")

    # Confirma que agora importa.
    try:
        import flwr  # noqa: F401
        print(f"flwr {flwr.__version__} importa sob NumPy 2.x ✅")
    except Exception as exc:  # noqa: BLE001
        print(f"AVISO: flwr ainda não importa: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
