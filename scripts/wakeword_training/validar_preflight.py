#!/usr/bin/env python
"""Validacion PRE-VUELO del pipeline de entrenamiento del wake word.

Por que existe:
    Un entrenamiento en Colab cuesta 40-90 minutos de GPU. Si despues el modelo
    sale colapsado, ese tiempo se perdio entero y nadie sabe por que.
    Este script comprueba ANTES de gastar nada lo que hoy solo se descubre al
    final: frases objetivo envenenando los negativos, rutas que el entrenador
    no lee, clips reales que se pierden en silencio, fuga entre(train y
    retenidos, o un modelo exportado que ya no discriminate.

Uso:
    # antes de entrenar (Colab o local)
    python scripts/wakeword_training/validar_preflight.py --raiz /content

    # despues de entrenar, sobre el modelo exportado
    python scripts/wakeword_training/validar_preflight.py --raiz /content \
        --modelo /content/zix_model/zix_model/zix.onnx --modo post

Codigo de salida:
    0 = todo correcto, se puede entrenar / el modelo sirve
    1 = hay errores criticos: NO entrenar
    2 = hay avisos: se puede entrenar, pero conviene mirarlos
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

RAIZ_SCRIPT = Path(__file__).resolve().parent
RAIZ_PROYECTO = RAIZ_SCRIPT.parents[1]

CRITICOS: list[str] = []
AVISOS: list[str] = []
OKS: list[str] = []


def critico(msg: str) -> None:
    CRITICOS.append(msg)


def aviso(msg: str) -> None:
    AVISOS.append(msg)


def ok(msg: str) -> None:
    OKS.append(msg)


def normalizar(frase: str) -> str:
    """Minusculas, sin acentos, sin puntuacion final, espacios colapsados.

    Los acentos importan: "hey zix" y "hey zíx" son la misma frase para el
    detector, asi que un negativo con tilde pasaria el filtro si solo
    normalizamos mayusculas.
    """
    f = unicodedata.normalize("NFKD", frase or "")
    f = "".join(c for c in f if not unicodedata.combining(c))
    f = f.strip().lower()
    f = re.sub(r"[.!?,;:]+$", "", f)
    f = re.sub(r"[^a-z0-9 ]+", " ", f)
    f = re.sub(r"\s+", " ", f)
    return f.strip()


def info(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1. Negativos: la frase objetivo NO puede estar
# ---------------------------------------------------------------------------
def validar_negativos(raiz: Path) -> None:
    info("\n[1] Frases objetivo en los negativos")
    sys.path.insert(0, str(RAIZ_SCRIPT))
    try:
        import generar_negativos  # type: ignore
    except Exception as exc:  # pragma: no cover
        aviso(f"no se pudo importar generar_negativos ({exc})")
        return

    frases_obj = [normalizar(f) for f in getattr(generar_negativos, "FRASES_OBJETIVO", ("hey zix",))]
    try:
        lista = generar_negativos.cargar_texto()
    except Exception as exc:
        critico(f"cargar_texto() fallo: {exc}")
        return

    if not lista:
        critico("cargar_texto() devuelve una lista vacia: no habria negativos")
        return

    offenders = sorted({t for t in lista if normalizar(t) in frases_obj})
    if offenders:
        critico(
            "FRASE OBJETIVO ENTRE LOS NEGATIVOS: "
            f"{offenders}. El modelo aprendera a ignorar la frase que debe "
            "despertar. Es la causa clasica del colapso."
        )
    else:
        ok(f"{len(lista)} negativos, ninguno es la frase objetivo")

    # Las confusables legitimas deben seguir ahi: si desaparecen, el filtro
    # es demasiado agresivo y el modelo pierde negativos duros.
    confusables = [t for t in lista if normalizar(t) not in frases_obj]
    if len(confusables) < 20:
        critico(
            f"quedan solo {len(confusables)} negativos utiles. "
            "Revisa que el filtro no este borrando confusables legitimas."
        )
    else:
        ok(f"{len(confusables)} confusables conservadas como negativo")


# ---------------------------------------------------------------------------
# 2. Rutas: deben coincidir con las que LEE el entrenador instalado
# ---------------------------------------------------------------------------
def _rutas_openwakeword() -> tuple[str, str] | None:
    try:
        import openwakeword  # type: ignore
    except Exception:
        return None
    train_py = Path(openwakeword.__file__).resolve().parent / "train.py"
    if not train_py.is_file():
        return None
    src = train_py.read_text(encoding="utf-8", errors="replace")
    m_pos = re.search(r'positive_train_output_dir\s*=\s*os\.path\.join\(([^)]+)\)', src)
    m_neg = re.search(r'negative_train_output_dir\s*=\s*os\.path\.join\(([^)]+)\)', src)
    if not (m_pos and m_neg):
        return None
    return m_pos.group(1), m_neg.group(1)


def validar_rutas() -> None:
    info("\n[2] Rutas del entrenador instalado")
    par = _rutas_openwakeword()
    if par is None:
        aviso("no se pudo leer train.py de openWakeWord; se omite la comprobacion de rutas")
        return
    pos_tpl, neg_tpl = par
    if '"positive_train"' not in pos_tpl:
        critico(f"openWakeWord ya no usa positive_train: {pos_tpl}")
    if '"negative_train"' not in neg_tpl:
        critico(f"openWakeWord ya no usa negative_train: {neg_tpl}")

    try:
        import inyectar_clips_reales as inj  # type: ignore
    except Exception as exc:
        aviso(f"no se pudo importar inyectar_clips_reales ({exc})")
        return

    pos = str(getattr(inj, "POS_TRAIN", "")).replace("\\", "/")
    neg = str(getattr(inj, "NEG_TRAIN", "")).replace("\\", "/")
    if pos.endswith("/positive/train") or "/positive/train" in pos:
        critico(
            f"inyectar_clips_reales usa 'positive/train' pero openWakeWord lee "
            "'<output_dir>/<model_name>/positive_train'. Los clips reales se "
            "pierden en una carpeta que nadie lee."
        )
    elif not pos.endswith("positive_train"):
        critico(f"la ruta de positivos no termina en positive_train: {pos}")
    else:
        ok(f"ruta de positivos correcta: {pos}")

    if neg and not neg.endswith("negative_train"):
        critico(f"la ruta de negativos no termina en negative_train: {neg}")
    elif neg:
        ok(f"ruta de negativos correcta: {neg}")


# ---------------------------------------------------------------------------
# 3. Clips reales: integridad y presencia
# ---------------------------------------------------------------------------
def validar_clips(raiz: Path) -> None:
    info("\n[3] Clips reales")
    candidatos = [
        raiz / "hey_zix_real",
        raiz.parent / "data" / "wakeword_real_16k",
        RAIZ_PROYECTO / "data" / "wakeword_real_16k",
    ]
    carpeta = next((c for c in candidatos if c.is_dir()), None)
    if carpeta is None:
        aviso("no se encontro carpeta de clips reales; se omite (puede ser normal en Colab antes de subir el zip)")
        return

    wavs = sorted(carpeta.glob("*.wav"))
    if not wavs:
        critico(f"la carpeta de clips reales esta vacia: {carpeta}")
        return

    try:
        import numpy as np
        import scipy.io.wavfile as wavfile
    except Exception as exc:
        aviso(f"sin numpy/scipy no se puede auditar el audio ({exc})")
        return

    malos_sr, vacios, pequenos = [], [], []
    for w in wavs:
        try:
            sr, data = wavfile.read(str(w))
            arr = np.asarray(data)
            if arr.size == 0:
                vacios.append(w.name)
                continue
            if int(np.abs(arr).max()) < 500:
                pequenos.append(w.name)
            if sr != 16000:
                malos_sr.append(f"{w.name}({sr}Hz)")
        except Exception as exc:
            vacios.append(f"{w.name}({type(exc).__name__})")

    info(f"     {carpeta}: {len(wavs)} wav")
    if malos_sr:
        critico(
            f"{len(malos_sr)} clips NO estan a 16 kHz: {malos_sr[:5]}. "
            "openWakeWord espera 16 kHz."
        )
    if vacios:
        critico(f"{len(vacios)} clips ilegibles o vacios: {vacios[:5]}")
    if pequenos:
        critico(f"{len(pequenos)} clips casi mudos (max<500): {pequenos[:5]}")
    if not (malos_sr or vacios or pequenos):
        ok(f"{len(wavs)} clips reales integros a 16 kHz y con señal")


# ---------------------------------------------------------------------------
# 4. Fuga: retenidos no deben estar en entrenamiento
# ---------------------------------------------------------------------------
def _firma(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validar_fuga(raiz: Path) -> None:
    info("\n[4] Fuga entre entrenamiento y retenidos")
    # El retenido real es zix_real_heldout (lo crea inject_real.py en Colab).
    # data/wakeword_real y data/wakeword_real_16k son el MISMO set en dos
    # formatos: compararlos entre si NO es fuga, es duplicacion de disco.
    held_dir = raiz / "zix_real_heldout"
    if not held_dir.is_dir():
        aviso("no hay carpeta de retenidos todavia (normal antes de entrenar)")
        return
    he = {p.name: _firma(p) for p in held_dir.glob("*.wav")}
    info(f"     retenidos: {held_dir} -> {len(he)} wav")
    fuentes = [
        raiz / "hey_zix_real",
        raiz / "zix_model" / "zix" / "positive_train",
        RAIZ_PROYECTO / "data" / "wakeword_real_16k",
    ]
    checked = False
    for src in [s for s in fuentes if s.is_dir()]:
        checked = True
        tr = {p.name: _firma(p) for p in src.glob("*.wav")}
        comunes = set(tr) & set(he)
        if comunes:
            critico(
                f"FUGA: {len(comunes)} clips estan a la vez en entrenamiento "
                f"({src}) y en retenidos: {sorted(comunes)[:5]}. "
                "El verificador daria un numero falso."
            )
        else:
            ok(f"sin fuga entre {src.name} ({len(tr)} wav) y {held_dir.name} ({len(he)} wav)")
    if not checked:
        aviso("no hay carpeta de clips reales de la que comparar")


# ---------------------------------------------------------------------------
# 5. Modelo exportado: esta colapsado?
# ---------------------------------------------------------------------------
def validar_modelo(modelo: Path, raiz: Path, n_clips: int = 6) -> None:
    info("\n[5] El modelo exportado discrimina?")
    if not modelo.is_file():
        aviso(f"no existe {modelo}: normal antes de entrenar")
        return
    try:
        import numpy as np
        import sys as _sys
        _sys.path.insert(0, str(RAIZ_PROYECTO / "src"))
        from zix.voice.openwakeword_wake_word import OpenWakeWordProvider
    except Exception as exc:
        aviso(f"no se pudo cargar el provider ({exc})")
        return

    try:
        prov = OpenWakeWordProvider(
            model=str(modelo), threshold=0.5, models_dir=str(modelo.parent)
        )
    except Exception as exc:
        critico(f"el modelo NO se pudo cargar con el provider de ZIX: {exc}")
        return
    ok(f"el modelo carga con OpenWakeWordProvider: {modelo.name}")

    rng = np.random.default_rng(7)
    silencio = np.zeros(16000 * 2, dtype=np.int16)
    ruido = (rng.normal(0, 8000, 16000 * 2)).astype(np.int16)
    tono = (8000 * np.sin(2 * np.pi * 440 * np.arange(16000 * 2) / 16000)).astype(np.int16)

    def maxscore(a: np.ndarray) -> float:
        b = 1280
        return max(
            float(prov._model.predict(a[i:i + b])[prov._key])
            for i in range(0, len(a) - b + 1, b)
        )

    import scipy.io.wavfile as wavfile

    def cargar(p):
        sr, d = wavfile.read(str(p))
        x = d.astype(np.float32)
        if x.ndim > 1:
            x = x.mean(axis=1)
        return (np.clip(x, -1, 1) * 32767).astype(np.int16)

    controles = {
        "silencio": maxscore(silencio),
        "ruido": maxscore(ruido),
        "tono440": maxscore(tono),
    }
    info("     controles: " + "  ".join(f"{k}={v:.6f}" for k, v in controles.items()))

    # Positivos: preferimos los RETENIDOS (los que el modelo no vio). Si no
    # existen todavia, usamos los clips reales y avisamos de que el recall sera
    # optimista, porque esos clips pudieron estar en el entrenamiento.
    pos_dir = raiz / "zix_real_heldout"
    optimista = False
    if not pos_dir.is_dir():
        pos_dir = RAIZ_PROYECTO / "data" / "wakeword_real_16k"
        optimista = True

    reales = []
    if pos_dir.is_dir():
        for w in sorted(pos_dir.glob("*.wav"))[:n_clips]:
            try:
                reales.append(maxscore(cargar(w)))
            except Exception:
                pass
    if not reales:
        aviso("sin clips reales para comparar: no se puede afirmar que el modelo sirva")
        return

    # Negativos: audio que NO debe disparar. En Colab, los clips de prueba del
    # propio entrenamiento; en local, las grabaciones de runtime/.
    neg_dir = raiz / "zix_model" / "zix" / "negative_test"
    if not neg_dir.is_dir():
        neg_dir = RAIZ_PROYECTO / "runtime"
    falsos = []
    if neg_dir.is_dir():
        for w in sorted(neg_dir.glob("*.wav"))[:n_clips * 4]:
            try:
                falsos.append(maxscore(cargar(w)))
            except Exception:
                pass

    umbral = 0.5
    aciertos = sum(1 for s in reales if s >= umbral)
    recall = aciertos / len(reales)
    far = (sum(1 for s in falsos if s >= umbral) / len(falsos)) if falsos else None

    info(f"     positivos={len(reales)} retenidos={'no' if optimista else 'si'} "
         f"recall@{umbral}={recall:.2%} max={max(reales):.4f} media={sum(reales)/len(reales):.4f}")
    if far is not None:
        info(f"     negativos={len(falsos)} falso_positivo_rate@{umbral}={far:.2%} "
             f"max={max(falsos):.4f}")

    # El criterio NO es 'el mejor clip supera el umbral'. Un modelo que solo
    # reconoce 1 de 23 clips de entrenamiento memorizo una instancia: no sirve.
    if recall < 0.5:
        critico(
            f"el modelo NO sirve: solo {aciertos}/{len(reales)} clips positivos "
            f"superan el umbral {umbral} (recall {recall:.0%}). "
            + (" esos clips pudieron estar en el entrenamiento, asi que el "
               "recuerdo real es aun peor. " if optimista else "")
            + "Un max alto aislado no compensa: el resto no se detecta."
        )
    elif far is not None and far > 0.02:
        critico(
            f"el modelo dispara demasiado: {far:.0%} de los negativos pasan el "
            f"umbral {umbral}. En uso real serian activaciones continuas."
        )
    else:
        ok(f"el modelo sirve: recall {recall:.0%} a umbral {umbral}"
           + (f", FAR {far:.1%}" if far is not None else " (sin negativos para medir FAR)"))


def validar_peso_real(raiz: Path) -> None:
    """Comprueba que la voz real llego AL SITIO que lee el entrenador.

    Es la asercion que faltaba: los 27 clips se podian copiar sin error a una
    carpeta que train.py nunca abre, y la corrida terminaba declarando
    exito. Aqui se comprueba el destino, no la intencion.
    """
    info("\n[6] Peso de la voz real en positive_train")
    pos = raiz / "zix_model" / "zix" / "positive_train"
    neg = raiz / "zix_model" / "zix" / "negative_train"
    if not pos.is_dir():
        aviso(f"aun no existe {pos}: se omite (normal antes de inyectar)")
        return

    reales = len(list(pos.glob("real_*_c*.wav")))
    total_pos = len(list(pos.glob("*.wav")))
    total_neg = len(list(neg.glob("*.wav"))) if neg.is_dir() else 0
    info(f"     reales={reales} positivos={total_pos} negativos={total_neg}")
    if reales == 0:
        critico(
            "0 clips reales en positive_train: el modelo se entrenara SOLO con "
            "voz sintetica y no reconocera al hablante real. Suele ser una ruta "
            "equivocada (positive/train en vez de positive_train)."
        )
    elif reales < total_pos * 0.05:
        aviso(
            f"la voz real es solo {100*reales/max(total_pos,1):.1f}% de los "
            f"positivos ({reales}/{total_pos}). Por debajo de ~5% la DNN suele "
            "no girar hacia el hablante real; sube ZIX_REAL_COPIAS."
        )
    else:
        ok(f"voz real = {100*reales/total_pos:.1f}% de los positivos ({reales})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validacion pre-vuelo del pipeline de wake word.")
    ap.add_argument("--raiz", default=".", help="raiz de trabajo (en Colab: /content)")
    ap.add_argument("--modelo", type=Path, default=None, help="modelo .onnx a validar")
    ap.add_argument("--modo", choices=["pre", "post"], default="pre",
                    help="pre = antes de entrenar; post = valida el modelo exportado")
    args = ap.parse_args()
    raiz = Path(args.raiz).resolve()

    print("=" * 74)
    print(f"  VALIDACION PRE-VUELO  ({'POST' if args.modo == 'post' else 'PRE'})   raiz={raiz}")
    print("=" * 74)

    validar_negativos(raiz)
    validar_rutas()
    validar_clips(raiz)
    validar_fuga(raiz)
    if args.modo == "post" or args.modelo:
        validar_modelo(args.modelo or (raiz / "zix_model" / "zix_model" / "zix.onnx"), raiz)
    validar_peso_real(raiz)

    print()
    print("=" * 74)
    for m in OKS:
        print(f"  [ok]      {m}")
    for m in AVISOS:
        print(f"  [aviso]   {m}")
    for m in CRITICOS:
        print(f"  [CRITICO] {m}")
    print("=" * 74)

    if CRITICOS:
        print(f"  RESULTADO: NO ENTRENAR. {len(CRITICOS)} error(es) critico(s).")
        return 1
    if AVISOS:
        print(f"  RESULTADO: se puede seguir, con {len(AVISOS)} aviso(s).")
        return 2
    print("  RESULTADO: todo correcto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())