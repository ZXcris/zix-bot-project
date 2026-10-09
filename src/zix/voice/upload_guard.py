"""Filtro local, previo a cualquier subida, del audio que va a transcribirse.

Por que existe (2026-10-09): `is_valid_order()` se ejecuta DESPUES de
transcribir, asi que a la altura de esa comprobacion el audio ya salio a
Groq. Este modulo filtra ANTES, y lo hace en LOCAL, sin red, para que un falso
positivo de la palabra de activacion no acabe enviando una conversacion ajena.

Que puede y que no puede decidir:

- Si descarta silencio y ruido porque el VAD lo dice sin necesidad de
  transcribir.
- NO puede decidir si el audio es una orden dirigida a ZIX: eso exige
  transcribir, y transcribir es justo lo que sube el audio. Por eso este filtro
  reduce el riesgo, no lo elimina. El cierre real es reentrenar el wake word
  para que responda a la voz del usuario y no a la de un podcast.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

SR = 16000
TRAMA_SILERO = 480  # 30 ms a 16 kHz


def _leer_int16(path: Path) -> Optional[tuple[int, "object"]]:
    """Devuelve (duracion_s, muestras int16 mono) o None si el WAV no sirve."""
    try:
        with wave.open(str(path), "rb") as w:
            canales, ancho, sr, n = (
                w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            )
            crudo = w.readframes(n)
    except (OSError, EOFError, wave.Error, ValueError):
        # wave lanza EOFError con ficheros truncados o basura, no solo OSError.
        # Este filtro corre DENTRO del bucle de audio: si revienta aqui, ZIX
        # deja de escuchar. Truncar el WAV no puede ser motivo para caerse.
        return None
    if ancho != 2 or canales < 1:
        return None

    import numpy as np

    x = np.frombuffer(crudo, dtype=np.int16)
    if canales > 1:
        x = x.reshape(-1, canales)[:, 0]
    if x.size == 0 or sr <= 0:
        return None
    return (x.size / sr), x


def fraccion_de_habla(path: Path) -> Optional[float]:
    """Proporcion de tramas que Silero marca como habla.

    Devuelve None si no se puede decidir (Silero ausente o WAV ilegible), y el
    llamante debe tratar None como "no hay informacion", no como "no hay voz".
    """
    leido = _leer_int16(path)
    if leido is None:
        return None
    _, muestras = leido
    if len(muestras) < TRAMA_SILERO:
        return None
    try:
        from openwakeword.vad import VAD
    except Exception:  # noqa: BLE001 - Silero es opcional
        return None
    try:
        vad = VAD()
        tramas = 0
        con_voz = 0
        for i in range(0, len(muestras) - TRAMA_SILERO + 1, TRAMA_SILERO):
            if vad.predict(muestras[i: i + TRAMA_SILERO], frame_size=TRAMA_SILERO) > 0.5:
                con_voz += 1
            tramas += 1
        return (con_voz / tramas) if tramas else None
    except Exception:  # noqa: BLE001 - un fallo del VAD no debe cortar el flujo
        return None


def decidir_subida(
    path: Path,
    *,
    permitir_nube: bool,
    es_nube: bool,
    minimo_fraccion: float = 0.15,
    max_segundos: float = 15.0,
) -> tuple[bool, str]:
    """Decide si el audio de `path` debe enviarse a transcribir.

    Devuelve (permitido, motivo). El motivo va al log y al usuario.

    Orden de las comprobaciones: primero el interruptor de nube, porque es la
    decision que el usuario ha tomado y debe prevalecer sobre cualquier otra.
    """
    if es_nube and not permitir_nube:
        return False, (
            "STT_ALLOW_CLOUD=0: no se envia audio a ningun servidor. "
            "Usa STT_PROVIDER=local para transcribir en este equipo."
        )

    leido = _leer_int16(path)
    if leido is None:
        return False, "No se pudo leer el WAV: no se sube nada."
    duracion, _ = leido

    if duracion > max_segundos:
        return False, (
            f"El audio dura {duracion:.1f} s y el tope es {max_segundos:.0f} s: "
            "no se sube (proteccion ante activaciones falsas)."
        )

    fraccion = fraccion_de_habla(path)
    if fraccion is not None and fraccion < minimo_fraccion:
        return False, (
            f"Silero solo detecta voz en el {fraccion*100:.0f}% del audio "
            f"(minimo {minimo_fraccion*100:.0f}%): descartado sin subir nada."
        )

    if fraccion is None:
        return True, "Sin VAD disponible: no se puede filtrar, se continua."
    return True, f"Voz detectada en el {fraccion*100:.0f}% del audio."
