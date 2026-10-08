# Changelog

Formato basado en Keep a Changelog. Versionado semantico.

## [No publicado]

## [0.2.0] - 2026-10-03

### Anadido

- **Interfaz completa** `LOGIN → DESCARGA → CONFIGURACIÓN → HOME → CHAT`
  migrada desde Open Design (`apps/zix-ui/`). Cuatro pantallas estaticas, sin
  dependencias externas.
- **CSP en las cuatro pantallas**, con `connect-src 'none'`.
- **Herramientas del wake word**:
  - `grabar_clips.py`: grabador guiado que valida cada toma (duracion, nivel,
    clipping y habla detectada con Silero) y cubre una matriz de 9 condiciones.
  - `verify_heldout.py`: verifica el modelo **solo** sobre clips retenidos,
    rechaza carpetas de entrenamiento y propone umbral con margen.
- **337 pruebas** (`pytest`).
- Documentacion de gobierno: `LICENSE` (GPL-3.0), `NOTICE.md`,
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
  `.gitattributes`, `.editorconfig` y CI en GitHub Actions.

### Cambiado

- Home muestra estados vacios honestos en vez de datos de ejemplo: nada de
  "GPT-4o", "70%" ni "21 de 30 dias utilizados".
- Home → Chat conectado: "Nueva conversacion" navega y pasa el contexto por
  `sessionStorage`.

### Corregido

- El boton de menu de Chat declara `aria-expanded` y lo sincroniza al abrir y
  cerrar la barra lateral.
- La clave de cobertura del grabador usaba un orden distinto al del nombre de
  archivo, y la rotacion de condiciones nunca avanzaba.

### Seguridad

- Purga de datos personales del historial: correo, identificador de Drive y
  rutas absolutas con el usuario del sistema.
- `zix.onnx` deja de distribuirse: entrenado con FMA (CC-BY-NC, no comercial) y
  con 15% de acierto real.
- `graphify-out/` deja de versionarse: 3,3 MB generados con rutas del sistema.

## [0.1.0]

- Pipeline de voz: captura con WASAPI, wake word con openWakeWord, VAD por RMS,
  STT con Groq Whisper, agent con herramientas y TTS local con Piper.
- UI inicial (`apps/zix-ui/index.html`), hoy legacy.
