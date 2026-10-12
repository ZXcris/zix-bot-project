"""Parche de openWakeWord: sustituye generate_adversarial_texts.

Por que: la version original depende de DeepPhonemizer, que hoy descarga un
HTML de error en vez del modelo de espeak y revienta con

    pickle.UnpicklingError: invalid load key, b'<'
    train.py:709 -> data.py:963 generate_adversarial_texts()

Como esta funcion solo produce frases NEGATIVAS difíciles (variaciones de
"Hey ZIX"), se reemplaza por un generador propio de confusables. No cambia lo
que el modelo aprende sobre la frase objetivo; solo evita que el entrenamiento
reviente al empezar.
"""

RUTA = "/content/openwakeword/openwakeword/data.py"

NUEVA = '''def generate_adversarial_texts(input_text, N=20, include_partial_phrase=0.2, include_input_words=0.2):
    """Parche ZIX: confusables de "Hey ZIX" sin depender de DeepPhonemizer.

    El original usa DeepPhonemizer, que ya no descarga su checkpoint (devuelve
    HTML y UnpicklingError). Estas frases se sintetizan igual con piper y
    cumplen el mismo papel: negativos que suenan parecido al objetivo.
    """
    import logging as _logging

    palabras = str(input_text).lower().replace(",", " ").split()
    if not palabras:
        return []

    # variantes por posicion: 0 = palabra de inicio, 1.. = el resto
    INICIO = ["hey", "hey", "hey", "a", "ah", "ei", "hey uh", "they", "ha"]
    MEDIO = {
        "zix": ["zix", "zix", "zik", "zik", "six", "six", "zics", "zixx",
                "zicks", "zixs", "zi", "ziks", "ziz", "zex", "zyx", "zixi",
                "zic", "zips", "zisp"],
        "jarvis": ["jarvis", "jarvis", "jarv", "jarvez", "chavis", "carvis",
                   "jarviss", "javis", "jarbis", "jarv"],
    }
    FIN = ["", "", "", "computer", "assistant", "por favor", "ahora", "ayuda"]

    out = []
    for ini in INICIO:
        for med in MEDIO.get(palabras[-1], [palabras[-1]]):
            out.append((ini + " " + med).strip())
            for fin in FIN:
                if fin:
                    out.append((ini + " " + med + " " + fin).strip())
    # la frase tal cual, con cada palabra sustituida por una variante
    for i in range(len(palabras) - 1):
        for med in MEDIO.get(palabras[-1], [palabras[-1]]):
            aux = list(palabras)
            aux[i] = INICIO[i % len(INICIO)]
            aux[-1] = med
            out.append(" ".join(aux))
    # parciales: solo la primera palabra, solo la ultima
    out.append(palabras[0])
    out.append(palabras[-1])
    out.append(palabras[0] + " " + palabras[-1])

    # CRITICO: quitar la frase exacta. Estas clips se sintetizan como
    # NEGATIVOS; si una dice exactamente "hey zix", se entrena al modelo para
    # ignorar la frase objetivo y el wake word nunca dispara.
    exacta = " ".join(palabras)
    out = [x for x in out if x != exacta]

# 'dict.fromkeys' conserva el orden y quita duplicados. Ojo: dentro de una
    # comprehension el iterable se evalua en el ambito EXTERNO, asi que no
    # puede referring-se a la propia variable del bucle.
    out = list(dict.fromkeys([x for x in out if x]))
    assert exacta not in out, "la frase exacta no puede estar entre las negativas"
    try:
        N = int(N)
    except Exception:
        N = 20
    if N and len(out) > N:
        out = out[:N]
    _logging.warning(
        "adversarial: DeepPhonemizer no disponible; %d confusables generados a mano",
        len(out),
    )
    return out
'''

with open(RUTA) as f:
    lineas = f.readlines()

ini = None
for i, ln in enumerate(lineas):
    if ln.startswith("def generate_adversarial_texts("):
        ini = i
        break

if ini is None:
    print("ERROR: no encuentro generate_adversarial_texts")
    raise SystemExit(1)

# la funcion termina en la siguiente linea que empieza por 'def ' o '@' en col 0
fin = len(lineas)
for j in range(ini + 1, len(lineas)):
    s = lineas[j]
    if s.startswith("def ") or s.startswith("@") or s.startswith("class "):
        fin = j
        break

print(f"reemplazo lineas {ini+1}..{fin} ({fin-ini} lineas) por {len(NUEVA.splitlines())}")
nuevas = lineas[:ini] + [NUEVA] + lineas[fin:]
with open(RUTA, "w") as f:
    f.writelines(nuevas)

import py_compile

py_compile.compile(RUTA, doraise=True)
print("ADVERSARIAL_PATCH_OK")

# comprobacion rapida
import importlib.util
spec = importlib.util.spec_from_file_location("oww_data_check", RUTA)
# no se importa el modulo entero (arrastra torch): se extrae la funcion sola
src = "".join(open(RUTA).readlines()[ini:ini + len(NUEVA.splitlines()) + 1])
ns = {}
exec(src, ns)
out = ns["generate_adversarial_texts"]("hey zix", N=300)
print(f"muestra ({len(out)} frases):")
for o in out[:8]:
    print("   ", repr(o))
assert any("zix" in o for o in out), "debe incluir variantes de zix"
assert not any("hey zix" == o for o in out[:1]), "no debe devolver la frase exacta primero"
print("PRUEBA_OK")