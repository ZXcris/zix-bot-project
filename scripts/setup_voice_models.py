"""Configuración de los modelos de voz de ZIX (opt-in, no lo toca pytest).

Descarga/configura (idempotente, solo si falta):
  1. Modelos de openWakeWord (hey_jarvis + feature models) -> recursos del
     paquete openwakeword (descarga oficial de GitHub releases).
  2. Voz de Piper es_MX-claude-high (.onnx + .onnx.json) -> models/piper/
     desde HuggingFace (rhasspy/piper-voices, fuente oficial).
     Voz anterior es_MX-ald-medium queda como respaldo si ya existe.
  3. Datos de espeak-ng -> %LOCALAPPDATA%\\zix\\espeak-ng-data (ruta ASCII:
     espeak-ng del wheel de piper no lee rutas con caracteres no-ASCII,
     p. ej. "Imágenes" en la ruta del proyecto).

Uso:
    python scripts/setup_voice_models.py

Requiere conexión a internet. Nunca imprime secretos.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zix.config import Config  # noqa: E402

def _piper_base_url(model_name: str) -> str:
    """Construye la URL base en HuggingFace para cualquier voz Piper es_*.

    Formato esperado: {locale}-{speaker}-{quality}, p. ej.
    es_MX-ald-medium -> es/es_MX/ald/medium,
    es_MX-claude-high -> es/es_MX/claude/high.
    """
    parts = model_name.split("-")
    if len(parts) != 3 or not parts[0].startswith("es_"):
        raise RuntimeError(
            f"Nombre de voz Piper no válido: {model_name!r}. "
            "Esperado formato 'es_MX-ald-medium'."
        )
    locale, speaker, quality = parts
    return (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        f"es/{locale}/{speaker}/{quality}"
    )


def _download(url: str, dest: Path, expected_bytes: int | None = None) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expected_bytes is not None:
        if dest.stat().st_size == expected_bytes:
            print(f"  ya existe: {dest.name} ({dest.stat().st_size} bytes)")
            return
    print(f"  descargando {dest.name} ...")
    urllib.request.urlretrieve(url, dest)
    size = dest.stat().st_size
    if expected_bytes is not None and size != expected_bytes:
        raise RuntimeError(
            f"Tamaño inesperado para {dest.name}: {size} != {expected_bytes}"
        )
    print(f"  OK: {dest.name} ({size} bytes)")


def setup_wake_word_models() -> None:
    print("[1/3] Modelos de openWakeWord (hey_jarvis + feature models)")
    from openwakeword import utils

    utils.download_models(["hey_jarvis_v0.1"])
    print("  OK: modelos de openWakeWord listos.")


def setup_piper_voice() -> None:
    config = Config.from_env()
    model_name = config.piper_voice
    dest_dir = Path(config.piper_models_dir).resolve()
    base_url = _piper_base_url(model_name)
    print(f"[2/3] Voz de Piper: {model_name} -> {dest_dir}")

    _download(f"{base_url}/{model_name}.onnx", dest_dir / f"{model_name}.onnx")
    _download(
        f"{base_url}/{model_name}.onnx.json",
        dest_dir / f"{model_name}.onnx.json",
    )
    print("  OK: voz de Piper lista.")


def setup_espeak_data() -> None:
    config = Config.from_env()
    dest = Path(config.piper_espeak_data_dir).resolve()
    phontab = dest / "phontab"
    if phontab.exists():
        print(f"  ya existe: {dest}")
        return
    import piper

    src = Path(piper.__file__).resolve().parent / "espeak-ng-data"
    if not (src / "phontab").exists():
        raise RuntimeError(f"El paquete piper no incluye espeak-ng-data: {src}")
    if not dest.as_posix().isascii():
        raise RuntimeError(
            f"La ruta destino no es ASCII y espeak-ng no la leerá: {dest}"
        )
    print(f"  copiando espeak-ng-data -> {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copytree(src, dest, dirs_exist_ok=True)
    if not phontab.exists():
        raise RuntimeError(f"Fallo copiando espeak-ng-data a {dest}")
    print("  OK: espeak-ng-data listo.")


def check_bundled_zix_model() -> None:
    """Verifica el wake word propio (viaja con el repo, nunca se descarga).

    El .onnx usa external data: zix.onnx.data debe estar junto a zix.onnx.
    """
    from zix.config import project_path

    model = project_path("models/wakeword/zix.onnx")
    data = project_path("models/wakeword/zix.onnx.data")
    print("[3/3] Wake word propio: models/wakeword/zix.onnx")
    if not model.is_file() or model.stat().st_size == 0:
        raise RuntimeError(
            "Falta models/wakeword/zix.onnx (debería venir con el repositorio). "
            "Se usará hey_jarvis como respaldo hasta conseguirlo."
        )
    if not data.is_file():
        raise RuntimeError(
            "Falta models/wakeword/zix.onnx.data junto al .onnx "
            "(onnxruntime lo exige para cargar los pesos)."
        )
    print(f"  OK: zix.onnx ({model.stat().st_size} bytes) + .data presente.")
    print("  Actívalo con WAKE_WORD_MODEL=zix en .env")


def main() -> int:
    setup_wake_word_models()
    setup_piper_voice()
    setup_espeak_data()
    check_bundled_zix_model()
    print()
    print("Modelos de voz configurados.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - mostrar el error exacto
        print(f"\nERROR configurando modelos: {type(exc).__name__}: {exc}")
        sys.exit(1)