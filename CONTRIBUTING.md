# Cómo contribuir en ZIX

ZIX es un asistente de voz para Windows: `micrófono → wake word → STT → agent →
herramientas → TTS → altavoz`.

## Antes de nada

ZIX está bajo **GPL-3.0-or-later**, forzado por `piper-tts`. Cualquier
contribución se publica bajo la misma licencia. Ver `NOTICE.md` para el detalle
de por qué.

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env      # y rellena tus claves
.\.venv\Scripts\python.exe -m pip install git-filter-repo   # si vas a tocar el historial
```

En Windows, `sounddevice` necesita **PortAudio**. Sin él, la captura de audio
no arranca.

## Reglas del proyecto

1. **El núcleo no importa SDKs concretos.** `src/zix/core/` (Agent,
   ToolRegistry, ToolExecutor) nunca debe hacer `import groq` ni similar. Un
   proveedor se añade detrás de la interfaz `AIProvider`. Hay un test que lo
   vigila.
2. **Zonas calientes: `src/zix/voice/`, `conversation.py` y `config.py`.**
   Cambiarlas afecta al bucle de audio en vivo. Avisa antes de tocarlas.
3. **Nada de datos ficticios en la interfaz.** Si una pantalla no puede mostrar
   algo real, muestra un estado vacío honesto. No pongas un "70%" de ejemplo ni
   un modelo inventado: la UI ya se limpió de eso y no queremos volver.
4. **Sin secretos en el repo.** Las claves van en `.env`, que está en
   `.gitignore`. `.env.example` solo lleva campos vacíos.
5. **Sin datos personales versionados.** Ni correos, ni rutas absolutas de tu
   máquina, ni identificadores de Drive. Si un script los genera, que los
   escriba en `%TEMP%`.
6. **Artefactos generados no se versionan.** `graphify-out/`, `runtime/`,
   `models/` y las grabaciones están en `.gitignore` a propósito.
7. **Verificar el wake word solo con voz retenida.** Nunca con los clips de
   entrenamiento: `scripts/wakeword_training/verify_heldout.py` lo impide
   incluso, y avisa si le pasas una carpeta de entrenamiento.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Ahora hay **336 tests**. Antes de abrir un PR:

- Los tests nuevos van en `tests/`.
- Los scripts de `scripts/` que no los ejecuta pytest son *opt-in*: si contienen
  lógica pura, añade tests para esa lógica (mira `tests/test_wakeword_tools.py`).
- Si tocas la UI, actualiza también la copia en Open Design, o el diseño y el
  código se desincronizan.

## Commits

Mensaje en español, imperativo, y explica el porqué cuando no es evidente. Los
hashes son inmutables: si necesitas reescribir historia para quitar un secreto,
usa `git filter-repo` y avisa antes de hacer `--force-with-lease`.

## Flujo de trabajo

Ramas `main` / `cristian/<tema>` / `primo/<tema>`, PR con revisión y **sin
force-push** sobre ramas compartidas.
