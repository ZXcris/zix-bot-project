"""Graba clips reales de "Hey ZIX" para reentrenar (opt-in, no lo toca pytest).

Modo guiado: te dice que condicion falta, pulsas Enter, dices "Hey ZIX",
y el clip se valida solo (duracion, nivel, clipping y habla detectada con
Silero). Los tomas malos se rechazan en el momento, no luego.

Uso:
    python scripts/wakeword_training/grabar_clips.py
    python scripts/wakeword_training/grabar_clips.py --persona ana
    python scripts/wakeword_training/grabar_clips.py --segundos 3 --destino data/wakeword_real

Guarda en data/wakeword_real/heyzix_<persona>_<condicion>_<nn>.wav
Nunca toca models/ ni .env.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _audio_utils import (  # noqa: E402 - hay que ajustar path antes
    downsample,
    medir,
    resample,
    save_wav,
    speech_fraction,
    to_int16,
)

# La matriz del protocolo (data/wakeword_real/README.md), en orden de prioridad.
# La intencion es cubrir variedad, no cantidad: 30 clips bien repartidos valen
# mas que 100 en el mismo sitio.
CONDICIONES = [
    ("cerca", "cuarto", "silencio"),
    ("cerca", "cuarto", "musica"),
    ("cerca", "cuarto", "ruido"),
    ("medio", "cocina", "silencio"),
    ("medio", "cocina", "musica"),
    ("medio", "cocina", "ruido"),
    ("lejos", "cuarto", "silencio"),
    ("lejos", "cuarto", "musica"),
    ("lejos", "ventana", "ruido"),
]

UMBRALES = {
    "min_segundos": 0.7,
    "max_segundos": 4.0,
    "min_rms": 0.01,
    "max_rms": 0.7,
    "min_pico": 0.05,
    "max_pico": 0.98,
    "min_habla": 0.08,
    "max_habla": 0.85,
}


def resolver_dispositivo(preferencia: str | None) -> tuple[int | None, str]:
    """Devuelve (id, etiqueta). preferencia: cadena contenida en el nombre."""
    import sounddevice as sd

    dispositivos = sd.query_devices()
    entrada = [i for i, d in enumerate(dispositivos) if d["max_input_channels"] > 0]
    if not entrada:
        raise SystemExit("ERROR: no hay ningun dispositivo de entrada.")
    if preferencia:
        for i in entrada:
            if preferencia.lower() in str(dispositivos[i]["name"]).lower():
                return i, str(dispositivos[i]["name"])
        raise SystemExit(f"ERROR: ningun micro coincide con {preferencia!r}.")
    defecto = sd.default.device[0]
    if defecto is not None and defecto >= 0:
        return int(defecto), str(dispositivos[defecto]["name"])
    return entrada[0], str(dispositivos[entrada[0]]["name"])


def grabar(dispositivo: int, segundos: float, sr_nativo: int) -> np.ndarray:
    import sounddevice as sd

    print(f"  grabando {segundos:.0f}s... (habla ahora)", flush=True)
    audio = sd.rec(int(segundos * sr_nativo), samplerate=sr_nativo,
                   channels=2, dtype="float32", device=dispositivo)
    sd.wait()
    return downsample(audio)


def validar(data: np.ndarray) -> tuple[bool, str]:
    dur, rms, pico = medir(data)
    if not (UMBRALES["min_segundos"] <= dur <= UMBRALES["max_segundos"]):
        return False, f"duracion {dur:.2f}s fuera de rango"
    if rms < UMBRALES["min_rms"] or pico < UMBRALES["min_pico"]:
        return False, f"demasiado bajo (rms={rms:.4f} pico={pico:.3f})"
    if pico > UMBRALES["max_pico"]:
        return False, f"clipping (pico={pico:.3f}), baja el microfono y repite"
    if rms > UMBRALES["max_rms"]:
        return False, f"nivel saturante (rms={rms:.3f})"
    habla = speech_fraction(to_int16(data))
    if habla < UMBRALES["min_habla"]:
        return False, f"no detecto habla (Silero {habla*100:.0f}%), di la frase al microfono"
    if habla > UMBRALES["max_habla"]:
        return False, f"demasiada habla continua (Silero {habla*100:.0f}%), parece ruido"
    return True, f"{dur:.2f}s rms={rms:.3f} pico={pico:.3f} habla={habla*100:.0f}%"


def _clave(dist: str, lugar: str, fondo: str) -> str:
    """Orden del nombre de archivo: <lugar>-<distancia>-<fondo> (ver README)."""
    return f"{lugar}-{dist}-{fondo}"


def siguiente_condicion(existentes: list[str]) -> tuple[tuple[str, str, str], int]:
    """Condicion menos cubierta. Devuelve ((dist, lugar, fondo), cuantos hay)."""
    recuento = Counter()
    for nombre in existentes:
        if not nombre.startswith("heyzix_"):
            continue
        partes = nombre[: -len(".wav")].split("_")
        if len(partes) >= 4:
            recuento[partes[2]] += 1
    elegida = min(CONDICIONES, key=lambda c: (recuento[_clave(*c)], CONDICIONES.index(c)))
    return elegida, recuento[_clave(*elegida)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Graba clips reales Hey ZIX guiados.")
    ap.add_argument("--persona", default="cristian", help="etiqueta de hablante en el nombre")
    ap.add_argument("--destino", default="data/wakeword_real")
    ap.add_argument("--segundos", type=float, default=3.0)
    ap.add_argument("--objetivo", type=int, default=len(CONDICIONES) * 3,
                    help="clips a cubrir (por defecto 3 por condicion)")
    ap.add_argument("--dispositivo", default=None, help="subcadena del nombre del micro")
    args = ap.parse_args()

    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)

    try:
        dispositivo, nombre_dev = resolver_dispositivo(args.dispositivo)
    except SystemExit as exc:
        print(exc)
        return 1

    import sounddevice as sd
    info = sd.query_devices(dispositivo)
    sr_nativo = int(info["default_samplerate"]) or 16000

    print("=" * 72)
    print(f"  micro  : {nombre_dev}")
    print(f"  destino: {destino.resolve()}")
    print(f"  sesion  : {args.persona}, objetivo {args.objetivo} clips")
    print("  Enter = grabar   q = salir")
    print("=" * 72)
    print("  Di SOLO 'Hey ZIX' una vez, con tono normal. Ni grites ni susurres.\n")

    buenos = malos = 0
    while True:
        existentes = sorted(p.name for p in destino.glob("*.wav"))
        if buenos >= args.objetivo:
            print(f"\nObjetivo cumplido: {buenos} clips validos.")
            break
        (dist, lugar, fondo), cuantos = siguiente_condicion(existentes)
        restantes = args.objetivo - buenos
        print(f"  [{buenos}/{args.objetivo}] siguiente: {lugar} / {dist} / {fondo}  "
              f"(hay {cuantos})   -   pulsado Enter para grabar", end="", flush=True)
        respuesta = sys.stdin.readline()
        if respuesta == "":
            # EOF (redireccion o tuberia cerrada): no se puede seguir interactuando.
            print("\n  (entrada cerrada, saliendo)")
            break
        if respuesta.strip().lower() == "q":
            break

        try:
            nativo = grabar(dispositivo, args.segundos, sr_nativo)
        except Exception as exc:  # noqa: BLE001 - el micro puede fallar, no pasa nada
            print(f"  [!] error al grabar: {exc}")
            continue

        data = resample(nativo, sr_nativo)
        ok, motivo = validar(data)
        if not ok:
            malos += 1
            print(f"  [X] rechazado: {motivo}. No se guarda nada. Repite.")
            time.sleep(0.2)
            continue

        existentes = sorted(p.stem for p in destino.glob("*.wav") if p.stem.startswith("heyzix_"))
        usados = set()
        for stem in existentes:
            if len(stem.split("_")) >= 4:
                usados.add(stem)
        cond = f"{lugar}-{dist}-{fondo}"
        n = 1
        while f"heyzix_{args.persona}_{cond}_{n:02d}" in usados:
            n += 1
        nombre = f"heyzix_{args.persona}_{cond}_{n:02d}.wav"
        save_wav(destino / nombre, data)
        buenos += 1
        print(f"  [OK] guardado {nombre}  ({motivo})")

    print(f"\n  Resumen: {buenos} validos, {malos} rechazados.")
    if buenos:
        print(f"  Siguiente paso:")
        print(f"    .venv\\Scripts\\python.exe scripts\\wakeword_training\\prepare_real_clips.py "
              f"{destino} --out data\\wakeword_real_16k")
    return 0


if __name__ == "__main__":
    sys.exit(main())
