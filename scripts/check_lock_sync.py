"""Comprueba que requirements.lock esta sincronizado con lo declarado.

Por que existe esto:

    requirements.lock fija las versiones con hashes; requirements.txt y
    requirements-dev.txt declaran QUE hace falta, sin fijar. Si alguien
    anade una dependencia nueva a los ficheros declarados y no regenera el
    lock, el entorno reproducible se queda viejo y nada lo dice: el CI
    instala bien, los tests pasan, y el fichero que promete "esto es
    exactamente lo que se instala" ya no lo es. Es la deriva silenciosa
    que hace inutilizable un lockfile.

Que comprueba, en dos niveles:

    1. Que toda dependencia declarada exista en el lock, y que la version
       fijada SATISFAGA la restriccion declarada ('groq>=2.0' con
       'groq==1.6.0' en el lock es una incoherencia). Esto usa 'packaging';
       si no esta disponible, el paso 1 sigue funcionando y el 2 se avisa
       pero no rompe.
    2. Con --sin-huerfanos, que NO haya en el lock ninguna dependencia que
       nada declarado necesite. Este modo necesita que las dependencias
       esten INSTALADAS (usa los metadatos del entorno) y por eso se
       ejecuta despues de instalar, no antes.

Que NO se comprueba aqui (y por que):

    Que el lock contenga las transitivas de cada dependencia. Eso lo
    comprueba de verdad 'pip install --require-hashes -r requirements.lock',
    que es lo que hace el job de reproducibilidad del CI. Aqui solo se
    comprueba el primer nivel, que es el que se puede comprobar sin
    instalar nada.

Uso:
    python scripts/check_lock_sync.py
    python scripts/check_lock_sync.py --sin-huerfanos

Codigo de salida:
    0 = sincronizado
    1 = hay que regenerar requirements.lock
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Ficheros que declaran dependencias, y de donde sale cada paquete.
DECLARADOS = {
    "requirements.txt": "produccion",
    "requirements-dev.txt": "desarrollo",
}

LOCK = "requirements.lock"

# Paquetes que se declaran a proposito y NO deben estar en el lock.
#
# 'pip-audit' es la herramienta que audita el lock, no parte del entorno
# que audita. Meterla dentro crearia el mismo bucle: para comprobar que
# el auditor esta limpio habria que instalarlo, y al instalarlo se
# arrastrarian sus propias dependencias al lock.
EXCLUIDOS = {
    "pip-audit": "es la herramienta que audita el lock, no una dependencia del entorno",
}

# Paquetes que estan en el lock sin que nada declarado los pida, y a pesar
# de eso se quedan a proposito. Cada uno con su motivo.
EXCLUIDOS_POR_SI_MISMO = {
    "pip": "fijar tambien el instalador es lo que hace la instalacion reproducible",
}

# Paquetes cuyo metadato no se puede leer. Si alguno aparece, se salta en
# vez de inventar: un falso positivo aqui tumbaria el CI sin motivo.
SIN_METADATOS: set[str] = set()

# Se rellena al arrancar: solo se avisa de los metadatos que faltan PARA
# PAQUETES DEL LOCK, que son los que afectan a la comprobacion.
EN_EL_LOCK: set[str] = set()

# 'nombre[extra]>=1.2 ; marker' -> 'nombre'
_RE_NOMBRE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
# Linea de lock: 'nombre==version \'  o 'nombre==version'
_RE_LOCK = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)")


def normalizar(nombre: str) -> str:
    """Normaliza un nombre segun PEP 503 (minusculas y - en vez de . _)."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


def leer_declarados(ruta: Path) -> dict[str, str]:
    """Nombre normalizado -> la restriccion declarada (o '' si no lleva).

    Se guarda la restriccion tal cual, sin el nombre, para poder
    comprobarla despues contra la version fijada en el lock.
    """
    encontrados: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        # Los marcadores de entorno ('; python_version < "3.12"') describen
        # cuando aplica el requisito, no que version se quiere.
        linea = linea.split("#", 1)[0].split(";", 1)[0].strip()
        if not linea:
            continue
        if linea.startswith("-"):
            # Opcion de pip (-r, --index-url, --extra-index-url). No es un paquete.
            continue
        if "@" in linea:
            # Requisito directo a una URL: 'nombre @ https://...'
            parte = linea.split("@", 1)[0].strip()
            m = _RE_NOMBRE.match(parte)
            if m:
                encontrados[normalizar(m.group(1))] = ""
            continue
        m = _RE_NOMBRE.match(linea)
        if not m:
            continue
        nombre = normalizar(m.group(1))
        # Lo que va detras del nombre es la restriccion, quitando los extras
        # entre corchetes ('nombre[extra]>=1.0').
        resto = linea[m.end():]
        if resto.startswith("["):
            cierre = resto.find("]")
            if cierre != -1:
                resto = resto[cierre + 1:]
        encontrados[nombre] = resto.strip()
    return encontrados


def leer_lock(ruta: Path) -> dict[str, str]:
    """Nombre normalizado -> version fijada."""
    nombres: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        m = _RE_LOCK.match(linea)
        if m:
            nombres[normalizar(m.group(1))] = m.group(2)
    return nombres


def _dependencias_de(paquete: str) -> set[str]:
    """Dependencias obligatorias de un paquete instalado, ya normalizadas."""
    try:
        from importlib.metadata import PackageNotFoundError, requires
    except ImportError:  # pragma: no cover - Python < 3.8
        return set()
    try:
        requisitos = requires(paquete) or []
    except PackageNotFoundError:
        # Solo interesa si el paquete esta en el lock: si no, es que el
        # entorno tiene de mas, y eso no es un problema del lock.
        if paquete in EN_EL_LOCK:
            SIN_METADATOS.add(paquete)
        return set()
    salida: set[str] = set()
    for r in requisitos:
        # Los extras no se instalan ('extra == "train"'), asi que sus
        # dependencias no obligan a nada.
        if "extra ==" in r:
            continue
        m = _RE_NOMBRE.match(r)
        if m:
            salida.add(normalizar(m.group(1)))
    return salida


def comprobar_huerfanos(en_el_lock: set[str], declarados: dict[str, str]) -> list[str]:
    """Paquetes del lock que nada declarado necesita.

    Las raices son los paquetes declarados que ESTAN en el lock. Si un
    paquete declarado no esta en el lock (por ejemplo pip-audit, que se
    instala aparte), no puede ser raiz: sus dependencias tampoco
    pertenecen al entorno fijado, y por tanto estarian de mas.
    """
    raices = {p for p in declarados if p in en_el_lock} - set(EXCLUIDOS)
    alcanzables: set[str] = set()
    frontera = set(raices)
    while frontera:
        actual = frontera.pop()
        if actual in alcanzables:
            continue
        alcanzables.add(actual)
        for d in _dependencias_de(actual):
            if d not in alcanzables:
                frontera.add(d)
    huerfanos = sorted(
        p for p in en_el_lock
        if p not in alcanzables and p not in EXCLUIDOS_POR_SI_MISMO
    )
    return huerfanos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sin-huerfanos",
        action="store_true",
        help="ademas, comprueba que no haya en el lock dependencias que "
             "nada declarado necesite (necesita las deps instaladas)",
    )
    args = ap.parse_args()

    lock_path = RAIZ / LOCK
    if not lock_path.is_file():
        print(f"ERROR: no existe {LOCK}", file=sys.stderr)
        return 1

    en_el_lock = leer_lock(lock_path)
    EN_EL_LOCK.update(en_el_lock)

    declarados: dict[str, str] = {}
    origen: dict[str, str] = {}
    for nombre_fichero, entorno in DECLARADOS.items():
        ruta = RAIZ / nombre_fichero
        if not ruta.is_file():
            print(f"ERROR: no existe {nombre_fichero}", file=sys.stderr)
            return 1
        for paquete, restriccion in leer_declarados(ruta).items():
            declarados.setdefault(paquete, restriccion)
            origen.setdefault(paquete, entorno)

    faltan: list[str] = []
    for paquete in sorted(declarados):
        if paquete in EXCLUIDOS:
            continue
        if paquete not in en_el_lock:
            faltan.append(paquete)

    if faltan:
        print("ERROR: requirements.lock esta desfasado.", file=sys.stderr)
        for paquete in faltan:
            print(f"  - {paquete} (declarado en {origen[paquete]}) "
                  f"no esta en {LOCK}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Regenera el lock con las versiones fijadas, por ejemplo:", file=sys.stderr)
        print("  pip-compile --generate-hashes --output-file requirements.lock \\", file=sys.stderr)
        print("      requirements.txt requirements-dev.txt", file=sys.stderr)
        return 1

    # Segundo nivel: la version fijada debe satisfacer la restriccion declarada.
    # Necesita 'packaging'. Si no esta, se avisa y se sigue: el primer nivel
    # ya ha pasado y es el que mas se breakage detecta.
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version
    except ImportError:
        print("AVISO: 'packaging' no esta disponible; solo se ha comprobado "
              "que las dependencias declaradas existen en el lock.")
        print(f"OK: {LOCK} esta sincronizado con {len(declarados)} dependencias declaradas "
              f"({len(en_el_lock)} paquetes en total).")
        return 0

    incoherentes: list[str] = []
    for paquete, restriccion in sorted(declarados.items()):
        if paquete in EXCLUIDOS or not restriccion:
            continue
        fijada = en_el_lock.get(paquete)
        if fijada is None:
            continue
        try:
            spec = Requirement(f"{paquete}{restriccion}").specifier
        except Exception:
            # Restriccion que no se sabe interpretar: no es un motivo para
            # tumbar el CI, pero tampoco se da por buena en silencio.
            print(f"AVISO: no se pudo interpretar la restriccion de {paquete!r} "
                  f"({restriccion!r}); se omite.", file=sys.stderr)
            continue
        if spec and Version(fijada) not in spec:
            incoherentes.append(f"  - {paquete}: el lock fija {fijada}, "
                                 f"pero se declara {restriccion}")

    if incoherentes:
        print("ERROR: requirements.lock fija versiones que NO satisfacen lo "
              "declarado.", file=sys.stderr)
        for linea in incoherentes:
            print(linea, file=sys.stderr)
        print("", file=sys.stderr)
        print("Regenera el lock para que cumpla las restricciones actuales.",
              file=sys.stderr)
        return 1

    # Tercer nivel (opcional): dependencias huerfanas.
    if args.sin_huerfanos:
        huerfanos = comprobar_huerfanos(set(en_el_lock), declarados)
        if huerfanos:
            print("ERROR: requirements.lock tiene dependencias que nada "
                  "declarado necesita.", file=sys.stderr)
            for h in huerfanos:
                print(f"  - {h}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Suelen ser restos de una instalacion previa (por ejemplo, "
                  "la cadena de pip-audit). Quitalos del lock.", file=sys.stderr)
            return 1
        if SIN_METADATOS:
            print("AVISO: sin metadatos instalados para: "
                  f"{', '.join(sorted(SIN_METADATOS))}. La comprobacion de "
                  "huerfanos no pudo ser completa.", file=sys.stderr)

    print(f"OK: {LOCK} esta sincronizado con {len(declarados)} dependencias declaradas "
          f"({len(en_el_lock)} paquetes en total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
