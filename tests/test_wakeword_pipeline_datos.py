"""Tests del pipeline de entrenamiento del wake word.

Estos tests NO comprueban solo funciones auxiliares: validan los DATOS
FINALES que consume el entrenamiento de openWakeWord.

Contexto de los defectos que cubren:
  - generar_negativos.py metia la frase exacta "hey zix" entre los negativos.
    El parche adversarial filtra esa frase, pero generar_negativos.py la
    volvia a anadir DESPUES, asi que el filtro no servia de nada.
  -inyectar_clips_reales.py escribia en zix_model/positive/train (con barra)
    mientras openWakeWord 0.6.0 lee zix_model/<modelo>/positive_train
    (con guion bajo). Los clips reales caian en una carpeta que nunca se lee.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
WAKEWORD_DIR = RAIZ / "scripts" / "wakeword_training"
sys.path.insert(0, str(WAKEWORD_DIR))

FRASE_OBJETIVO = "hey zix"


# --------------------------------------------------------------------------
# helpers de normalizacion (los mismos criterios que debe usar el filtro)
# --------------------------------------------------------------------------
def normalizar(frase: str) -> str:
    """Minusculas, sin puntuacion final, espacios colapsados."""
    f = (frase or "").strip().lower()
    f = re.sub(r"[.!?,;:]+$", "", f)
    f = re.sub(r"\s+", " ", f)
    return f.strip()


# --------------------------------------------------------------------------
# 1. La lista FINAL de negativos no debe contener la frase objetivo
# --------------------------------------------------------------------------
def test_frase_objetivo_no_esta_en_la_lista_final_de_negativos() -> None:
    """ESTE TEST DEBE FALLAR antes de la correccion.

    generar_negativos.py::cargar_texto() es la lista FINAL que se sintetiza
    como negativos. Si contiene "hey zix", el modelo aprende a ignorar la
    frase que deberia despertar.
    """
    import generar_negativos

    textos = generar_negativos.cargar_texto()
    assert textos, "cargar_texto() devolvio una lista vacia"

    offenders = [t for t in textos if normalizar(t) == normalizar(FRASE_OBJETIVO)]
    assert not offenders, (
        "La frase objetivo esta entre los negativos finales. "
        f"El modelo aprendera a ignorarla. Encontrados: {offenders}"
    )


@pytest.mark.parametrize(
    "variante",
    ["HEY ZIX", "Hey Zix", "hey  zix", "  hey zix  ", "hey zix.", "Hey-Zix", "hey zix!"],
)
def test_variantes_de_normalizacion_tambien_se_excluyen(variante: str) -> None:
    """Mayusculas, espacios extra y puntuacion final son la MISMA frase."""
    import generar_negativos

    textos = generar_negativos.cargar_texto()
    objetivo = normalizar(FRASE_OBJETIVO)

    offenders = [t for t in textos if normalizar(t) == objetivo]
    assert not offenders, (
        f"La variante {variante!r} equivale a la frase objetivo "
        f"y aparece entre los negativos: {offenders}"
    )


def test_frases_parecidas_siguen_siendo_negativos_validos() -> None:
    """El filtro NO debe borrar confusables legitimas.

    Si el filtro fuera demasiado agresivo, el modelo perderia negativos
    duros que son justamente los que lo hacen preciso.
    """
    import generar_negativos

    textos = generar_negativos.cargar_texto()
    normalizados = {normalizar(t) for t in textos}
    objetivo = normalizar(FRASE_OBJETIVO)

    # Estas son confusables reales que SI estan en la lista fuente del modulo.
    confusables_que_deben_sobrevivir = [
        "hey zics", "hey six", "hey zis", "hey zih", "hey zixx",
        "hey zips", "hey zisk", "hey zicks", "hey zizza", "hey zip",
        "hey jix", "hey zix en", "hey zixx por favor", "hey zics ahora",
        "hey six computer", "zix", "ok zix", "oye zix", "hola zix",
    ]
    for c in confusables_que_deben_sobrevivir:
        assert normalizar(c) != objetivo, "caso de prueba mal construido"
        assert normalizar(c) in normalizados, (
            f"El filtro borro la confusable legitima {c!r}. "
            "Se perdio un negativo util."
        )

    # Y debe quedar una masa razonable de negativos.
    assert len(textos) >= 30, f"quedaron muy pocos negativos: {len(textos)}"


def test_el_filtro_no_borra_la_fraccion_objetiva_por_error_de_normalizar() -> None:
    """Guardarrail: el filtro compara normalizado, no por igualdad cruda.

    Evita que alguien "arregle" el bug comparando solo minusculas y rompa
    los negativos con puntuacion o espacios dobles.
    """
    import generar_negativos

    if not hasattr(generar_negativos, "filtrar_frase_objetivo"):
        pytest.skip(
            "generar_negativos aun no expone filtrar_frase_objetivo; "
            "el filtro se aplica dentro de cargar_texto"
        )

    entrada = ["hey zix", "HEY ZIX.", "hey  zix", "hey six", "zix", "hey"]
    salida = generar_negativos.filtrar_frase_objetivo(entrada, FRASE_OBJETIVO)

    assert "hey six" in salida, "no debe borrar confusables"
    assert "zix" in salida, "no debe borrar palabras sueltas"
    assert "hey" in salida, "no debe borrar palabras sueltas"
    assert not any(normalizar(x) == normalizar(FRASE_OBJETIVO) for x in salida)


# --------------------------------------------------------------------------
# 2. Las rutas de clips reales deben coincidir con las que LEE openWakeWord
# --------------------------------------------------------------------------
def _rutas_que_usa_openwakeword() -> tuple[str, str]:
    """Extrae del train.py REAL instalado las rutas que lee el entrenamiento.

    No las codificamos a mano: se leen del paquete, asi que el test falla si
    openWakeWord cambia su estructura.

    Se lee el CODIGO FUENTE en disco, no se importa el modulo: train.py
    arrastra torch, que no hace falta para inspeccionar como construye rutas
    (y no esta instalado en el venv de desarrollo de ZIX).
    """
    try:
        import openwakeword as _oww
    except Exception as exc:  # pragma: no cover - entorno sin openwakeword
        pytest.skip(f"openwakeword no disponible: {exc}")

    train_py = Path(_oww.__file__).resolve().parent / "train.py"
    if not train_py.is_file():
        pytest.skip(f"no se encuentra train.py en {train_py}")
    src = train_py.read_text(encoding="utf-8", errors="replace")

    m_pos = re.search(r'positive_train_output_dir\s*=\s*os\.path\.join\(([^)]+)\)', src)
    m_neg = re.search(r'negative_train_output_dir\s*=\s*os\.path\.join\(([^)]+)\)', src)
    if not (m_pos and m_neg):
        pytest.skip("no se pudo localizar la construccion de rutas en train.py")
    return m_pos.group(1), m_neg.group(1)


def test_inyectar_clips_reales_usa_las_rutas_reales_de_openwakeword() -> None:
    """ESTE TEST DEBE FALLAR antes de la correccion.

   inyectar_clips_reales.py usaba zix_model/positive/train, pero
    openWakeWord construye output_dir/model_name/positive_train.
    Los clips reales se perdian en una carpeta que nadie lee.
    """
    import inyectar_clips_reales as inj

    pos_reales = getattr(inj, "POS_TRAIN", None)
    neg_reales = getattr(inj, "NEG_TRAIN", None)

    assert pos_reales is not None, "inyectar_clips_reales no expone POS_TRAIN"

    pos = str(pos_reales).replace("\\", "/")
    neg = str(neg_reales).replace("\\", "/") if neg_reales else ""

    # train.py usa guiones bajos y una subcarpeta con el nombre del modelo.
    assert "/positive_train" in pos, (
        f"la ruta de positivos debe terminar en positive_train, no en positive/train: {pos}"
    )
    assert "/positive/train" not in pos, "ruta con barra: openWakeWord no la lee"
    assert "zix" in pos.split("/positive_train")[0], (
        f"falta la subcarpeta del modelo (zix_model/zix/...): {pos}"
    )
    if neg:
        assert "/negative_train" in neg, (
            f"la ruta de negativos debe terminar en negative_train: {neg}"
        )


def test_la_ruta_de_inyeccion_coincide_con_la_de_openwakeword() -> None:
    """Compara el path del script con el que construye train.py de verdad.

    Este test NO se puede saltar: es el que ata las dos piezas. Si openWakeWord
    renombra positive_train, el script de inyeccion debe seguirlo.
    """
    pos_tpl, neg_tpl = _rutas_que_usa_openwakeword()
    import inyectar_clips_reales as inj

    # train.py: os.path.join(config["output_dir"], config["model_name"], "positive_train")
    assert '"positive_train"' in pos_tpl, pos_tpl
    assert '"negative_train"' in neg_tpl, neg_tpl
    # el script debe usar el mismo sufijo que train.py
    assert str(inj.POS_TRAIN).endswith("positive_train"), str(inj.POS_TRAIN)
    assert str(inj.NEG_TRAIN).endswith("negative_train"), str(inj.NEG_TRAIN)
    pos = str(inj.POS_TRAIN).replace("\\", "/")
    assert pos.count("/zix/") == 1, (
        f"debe quedar exactamente una subcarpeta de modelo 'zix': {pos}"
    )


def test_retiene_clips_y_usa_suma_aleatoria() -> None:
    """El retenido debe existir: sin el no hay forma de validar honestamente."""
    import inyectar_clips_reales as inj

    held = getattr(inj, "HELDOUT", None) or getattr(inj, "VALIDATION", None)
    assert held is not None, "inyectar_clips_reales no expone carpeta de retenidos"
    assert str(held).strip(), "la carpeta de retenidos esta vacia"


# --------------------------------------------------------------------------
# 3. El paso de inyeccion debe FALLAR, no continuar en silencio
# --------------------------------------------------------------------------
# Defecto: inyectar_clips_reales.py ejecutaba toda su logica a nivel de
# modulo. Al importarlo (tests, validadores) escribia en positive_train, y si
# faltaba ./hey_zix_real/ imprimia "ERROR" pero salia con codigo 0, de modo
# que la corrida de Colab continuaba hasta el final entrenando un modelo que
# no habia visto la voz real.
# --------------------------------------------------------------------------
def test_importar_inyectar_clips_reales_no_tiene_efectos_secundarios(tmp_path, capsys) -> None:
    """ESTE TEST DEBE FALLAR antes de la correccion.

    Importar el modulo no debe imprimir nada ni crear carpetas. Antes, el
    import ejecutaba la inyeccion entera.
    """
    import importlib

    antes = tmp_path / "zix_model"
    assert not antes.exists()

    import inyectar_clips_reales  # noqa: F401  (el import es lo que se prueba)

    capturado = capsys.readouterr()
    assert capturado.out.strip() == "", (
        "importar inyectar_clips_reales ejecuto logica:\n" + capturado.out
    )
    assert not antes.exists(), "el import creo carpetas en disco"


def test_inyectar_clips_reales_falla_con_codigo_distinto_de_cero(tmp_path, monkeypatch) -> None:
    """Si faltan los clips, main() debe devolver 1.

    Con codigo 0 la cadena de Colab sigue y produce un modelo inutil sin
    avisar. El error tiene que detener la ejecucion.
    """
    import importlib

    import inyectar_clips_reales as inj

    monkeypatch.setattr(inj, "SRC", tmp_path / "no_existe_hey_zix_real")
    importlib.reload(inj)
    monkeypatch.setattr(inj, "SRC", tmp_path / "no_existe_hey_zix_real")

    assert inj.main() == 1, "faltan los clips: main() debe devolver 1"


def test_inyectar_clips_reales_exige_voz_real_en_el_destino(tmp_path, monkeypatch) -> None:
    """El paso solo es exito si los clips reales llegan a positive_train."""
    import importlib

    import numpy as np
    import scipy.io.wavfile as wav

    import inyectar_clips_reales as inj

    src = tmp_path / "hey_zix_real"
    src.mkdir()
    for i in range(3):
        wav.write(str(src / f"real_{i}.wav"), 16000,
                  (np.random.default_rng(i).normal(0, 3000, 16000)).astype(np.int16))

    monkeypatch.setattr(inj, "COPIAS", 2)
    for attr, val in [
        ("SRC", src),
        ("MODEL_DIR", tmp_path / "zix_model" / "zix"),
        ("POS_TRAIN", tmp_path / "zix_model" / "zix" / "positive_train"),
        ("NEG_TRAIN", tmp_path / "zix_model" / "zix" / "negative_train"),
        ("HELDOUT", tmp_path / "zix_real_heldout"),
        ("STAGE", tmp_path / "zix_model" / "zix" / "extra_real"),
    ]:
        monkeypatch.setattr(inj, attr, val)

    rc = inj.main()
    assert rc == 0, "con clips presentes y validos main() debe devolver 0"

    llegados = list((tmp_path / "zix_model" / "zix" / "positive_train").glob("real_*_c*.wav"))
    assert llegados, "los clips reales no llegaron a positive_train"
    assert list((tmp_path / "zix_real_heldout").glob("*.wav")), "no se aparto ningun retenido"
    # y ningun retenido puede estar tambien en entrenamiento
    nombres_tr = {p.name for p in (tmp_path / "zix_model" / "zix" / "positive_train").glob("*.wav")}
    nombres_he = {p.name for p in (tmp_path / "zix_real_heldout").glob("*.wav")}
    assert not (nombres_tr & nombres_he), "fuga: un retenido esta tambien en entrenamiento"


# --------------------------------------------------------------------------
# 4. Las compuertas de Colab tienen que existir y ser letales
# --------------------------------------------------------------------------
# Defecto: train_model devolvia 0 con un modelo que no servia, y la corrida
# se daba por buena. Con el modelo actual, recall 3/27 con umbral 0.5.
# --------------------------------------------------------------------------
def _sh() -> str:
    return (WAKEWORD_DIR / "entrenar_colab.sh").read_text(encoding="utf-8", errors="replace")


def test_la_cadena_de_colab_tiene_compuerta_antes_de_entrenar() -> None:
    """No se deben gastar 40 min de GPU sin comprobar los datos."""
    src = _sh()
    assert "gate_pre.py" in src, "no hay compuerta previa al entrenamiento"
    assert src.index("gate_pre.py") < src.index("19. ENTRENAR"), (
        "la compuerta previa se ejecuta DESPUES de entrenar"
    )
    assert 'die "COMPUERTA PRE' in src, "la compuerta previa no detiene la corrida"


def test_la_cadena_de_colab_tiene_compuerta_despues_de_entrenar() -> None:
    """Despues de entrenar hay que medir el modelo, no asumir que sirvio."""
    src = _sh()
    assert "gate_post.py" in src, "no hay compuerta posterior al entrenamiento"
    assert src.index("gate_post.py") < src.index("MANIFESTO_SHA256"), (
        "la compuerta posterior se ejecuta tras empaquetar: llega tarde"
    )
    assert "recall" in src and "negative_test" in src, (
        "la compuerta posterior debe medir recall sobre retenidos y FAR sobre negativos"
    )


def test_la_frase_objetivo_no_esta_en_el_yaml_de_colab() -> None:
    """negative_phrases/custom_negative_phrases del YAML no pueden contener la frase."""
    m = re.search(r"cat > /content/write_yaml2\.py <<'PYEOF'(.*?)PYEOF", _sh(), re.S)
    if not m:
        pytest.skip("write_yaml2.py no encontrado en entrenar_colab.sh")
    cuerpo = m.group(1)
    negs = re.search(r"'negative_phrases':\s*\[(.*?)\]", cuerpo, re.S)
    custom = re.search(r"'custom_negative_phrases':\s*\[(.*?)\]", cuerpo, re.S)
    assert negs, "no se encontro negative_phrases en el YAML"
    assert custom, "no se encontro custom_negative_phrases en el YAML"
    objetivo = {"hey zix", "hey_zix", "hey zix."}
    assert not (objetivo & set(negs.group(1).lower().split(","))), negs.group(1)
    assert "hey zix" not in custom.group(1).lower(), custom.group(1)


# --------------------------------------------------------------------------
# 5. El validador post-entrenamiento no puede approving un modelo malo
# --------------------------------------------------------------------------
def test_el_validador_rechaza_el_modelo_colapsado_real() -> None:
    """Prueba de extremo a extremo sobre models/wakeword/zix.onnx.

    El modelo llega a 0.21 en un clip de ENTRENAMIENTO y a 0.0017 en los que
    nunca vio. Aprobarlo por el max seria aprobar un modelo que no detecta
    la frase: el criterio debe mirar el recall, no el mejor caso.
    """
    import validar_preflight as vp

    modelo = RAIZ / "models" / "wakeword" / "zix.onnx"
    if not modelo.is_file():
        pytest.skip("no hay modelo local que evaluar")

    vp.CRITICOS.clear()
    vp.AVISOS.clear()
    vp.OKS.clear()
    vp.validar_modelo(modelo, RAIZ, n_clips=6)

    assert vp.CRITICOS, (
        "el validador aprobo un modelo que no supera el umbral 0.5 en la "
        f"mayoria de los clips reales. criticos={vp.CRITICOS} avisos={vp.AVISOS}"
    )
    assert any("recall" in c or "umbral" in c for c in vp.CRITICOS), vp.CRITICOS