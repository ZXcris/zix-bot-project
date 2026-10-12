"""Descarga solo los modelos de openWakeWord que ZIX necesita.

Por que existe esto en vez de un 'pip install' y ya:

openwakeword NO incluye sus ficheros .onnx en el paquete de PyPI. Sin ellos:

- el wake word no arranca (falta hey_jarvis_v0.1.onnx);
- el VAD de Silero no arranca, y el freno de privacidad del STT cierra,
  con lo que en STT_PROVIDER=groq no se transcribe nada.

Ademas, `download_models()` sin argumentos se baja los ~16 modelos (alarma,
meteorologia, Alexa...). Si UNO falla, revienta la llamada entera y te quedas
sin ninguno. Aqui se piden solo los tres que hacen falta, uno a uno, y se
comprueba al final que estan los tres. Si algo falla, el mensaje dice cual.

Uso:
    python scripts/setup_openwakeword_models.py
    python scripts/setup_openwakeword_models.py --comprobar
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Los unicos que ZIX necesita. Los demas (alarma, meteorologia, Alexa) no se
# usan en ningun sitio del codigo.
NECESARIOS = ["hey_jarvis_v0.1", "melspectrogram", "embedding_model"]

# Silero lo usa el freno del STT, no el wake word, y lo carga vad.py por su
# cuenta. No siempre viene en la lista de modelos de openwakeword.
VARIOS = ["silero_vad"]


def destino() -> Path:
    import openwakeword

    return Path(openwakeword.__file__).resolve().parent / "resources" / "models"


def instalar() -> int:
    from openwakeword.utils import download_models

    d = destino()
    print(f"Modelos en: {d}")

    fallos = []
    for nombre in NECESARIOS + VARIOS:
        try:
            print(f"  {nombre}...", flush=True)
            download_models(model_names=[nombre], target_directory=str(d))
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue
            fallos.append(f"{nombre}: {type(exc).__name__}: {exc}")

    print()
    faltan = comprobar(silencioso=True)
    for nombre, ruta in faltan:
        print(f"  FALTA  {ruta.name}  (de {nombre})")

    if fallos:
        print("\nErrores al descargar:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    if faltan:
        print(f"\nFaltan {len(faltan)} modelos. Revisa la red o descarga a mano.")
        return 1
    print("Modelos listos.")
    return 0


def comprobar(silencioso: bool = False) -> list[tuple[str, Path]]:
    """Devuelve [(de_quien, ruta)] de los que faltan. Vacio = todo bien."""
    d = destino()
    faltan = []
    for nombre in NECESARIOS:
        for sufijo in (".onnx",):
            ruta = d / f"{nombre}{sufijo}"
            if not ruta.exists() or ruta.stat().st_size < 1000:
                faltan.append((nombre, ruta))
    ruta = d / "silero_vad.onnx"
    if not ruta.exists() or ruta.stat().st_size < 1000:
        faltan.append(("silero_vad", ruta))
    if not silencioso:
        if faltan:
            print(f"Faltan {len(faltan)} modelos:")
            for nombre, ruta in faltan:
                print(f"  - {nombre} -> {ruta}")
        else:
            print("Todos los modelos estan presentes.")
    return faltan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--comprobar",
        action="store_true",
        help="solo verificar, sin descargar nada",
    )
    args = ap.parse_args()
    if args.comprobar:
        return 1 if comprobar() else 0
    try:
        return instalar()
    except ImportError:
        print(
            "openwakeword no esta instalado.\n"
            "  python -m pip install -e \".[dev]\""
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())