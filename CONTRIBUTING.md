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

### Paso obligatorio: descargar los modelos de openWakeWord

```powershell
.\.venv\Scripts\python.exe -c "from openwakeword.utils import download_models; download_models()"
```

Sin este paso **el VAD de Silero no arranca**, porque el paquete de pip **no
incluye** los ficheros `.onnx` (son unos 25 MB). Consecuencias si te lo saltas:

- El wake word no funciona: falta `hey_jarvis_v0.1.onnx`.
- El freno de privacidad del STT no puede decidir y **cierra**, así que con
  `STT_PROVIDER=groq` no se transcribe nada. Verás el motivo en el log.

El CI hace este paso antes de testear, por eso allí los tests de privacidad
tienen sentido. Si te salen rojos con algo parecido a *"Silero no esta
disponible"*, casi siempre es que falta esto.

Para una instalación **reproducible** (la recomendada al publicar una release):

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
```

`requirements.txt` lleva versiones sueltas para el día a día;
`requirements.lock` fija las 48 con sus hashes sha256 de PyPI. Instalar desde el
lockfile garantiza que recibes exactamente lo que se probó, aunque una
dependencia publique mañana una versión alterada o rota.

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
8. **No subas modelos entrenados.** Ni `*.onnx`, ni `*.tflite`, ni checkpoints.
   No es una cuestión de tamaño: el modelo se entrenó con FMA, que es
   **CC-BY-NC**, es decir *no comercial*. Si ese modelo entrara en el repo,
   esa restricción se arrastraría a todo el proyecto y nadie podría venderse
   ZIX. `NOTICE.md` explica el detalle; aquí basta con la regla: si necesitas
   subir uno, abre primero un issue y lo discutimos antes de entrenarlo.
9. **El audio no se versiona.** `.gitignore` bloquea `*.wav`, `*.mp3`, `*.zip`
   y `*.bundle`. Es deliberado: la voz es un dato biométrico. Si tu PR necesita
   una muestra de audio, coméntalo en el issue y se decide.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Ahora hay **366 tests** que pasan y 1 omitido. Antes de abrir un PR:

- Los tests nuevos van en `tests/`.
- Los scripts de `scripts/` que no los ejecuta pytest son *opt-in*: si contienen
  lógica pura, añade tests para esa lógica (mira `tests/test_wakeword_tools.py`).
- Si tocas la UI, actualiza también la copia en Open Design, o el diseño y el
  código se desincronizan.

## Comprobaciones antes de enviar

El CI corre cuatro trabajos: la suite en Windows y en Linux, las
comprobaciones de interfaz, `pip-audit` contra las CVEs conocidas, y un
escaneo de secretos sobre todo el historial.

En local, lo mismo en un paso:

```powershell
.\.venv\Scripts\python.exe -m pip install pre-commit
.\.venv\Scripts\python.exe -m pre_commit install
```

A partir de ahí, cada `git commit` pasa por el escaneo de secretos antes de
existir. No es obligatorio: quien no lo instale sigue trabajando sin drama,
porque el CI le comprueba lo mismo. Si alguna vez hay que saltárselo
(`--no-verify`), menciónalo en el PR.

## Commits

Mensaje en español, imperativo, y explica el porqué cuando no es evidente. Los
hashes son inmutables: si necesitas reescribir historia para quitar un secreto,
usa `git filter-repo` y avisa antes de hacer `--force-with-lease`.

## Flujo de trabajo

Ramas `main` / `cristian/<tema>` / `primo/<tema>`, PR con revisión y **sin
force-push** sobre ramas compartidas.
