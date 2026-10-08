# Flujo de trabajo en equipo — ZIX

`main` es la rama estable de ZIX. Nadie desarrolla funcionalidades grandes directamente sobre `main`: cada tarea vive en su rama, se revisa por Pull Request y se integra con merge.

## Ramas

- `main` — estable, siempre funcional. Solo recibe merges revisados.
- `cristian/<tema>` — ramas de Cristian (ej: `cristian/fix-wakeword`, `cristian/providers`).
- `primo/<tema>` — ramas del primo cuando se incorpore (ej: `primo/ui`, `primo/tools`). Todavía no crearlas: aún no tiene PC ni cuenta de GitHub.
- Nombres en minúsculas, con guiones, describiendo la tarea.

## Antes de trabajar

```text
git status
git branch
git log --oneline
revisar documentación
revisar trabajo reciente
```

1. `git status`: ¿árbol limpio o hay cambios a medias?
2. `git branch`: ¿estoy en mi rama o en `main`?
3. `git log --oneline -5`: ¿qué cambió desde mi última sesión?
4. Leer `README.md`, `docs/` y la wiki si la tarea los toca.
5. Revisar lo que el otro subió (`git pull`, historial, Pull Requests).

Regla principal: **primero entender el estado actual; después modificarlo.**

## Después de trabajar

```text
git diff
tests
git status
commit
push
Pull Request
```

1. `git diff`: revisar cada cambio propio antes de registrarlo.
2. `python -m pytest tests/`: todo verde antes de subir.
3. `git status` + `git add` selectivo (nunca secretos: `.env`, tokens, claves).
4. Commit pequeño con mensaje claro (qué + por qué, en español o inglés consistente).
5. `push` a tu rama (jamás force-push a `main`).
6. Pull Request hacia `main` y pedir revisión del otro.

## Revisión de código

- El revisor lee el diff completo, ejecuta los tests y prueba el cambio si afecta voz/audio.
- Se aprueba solo si: tests verdes, sin secretos, sin romper lo existente.
- Comentarios concretos (archivo:línea); el autor ajusta y vuelve a pedir revisión.

## Merge y conflictos

- Merge a `main` solo tras aprobación. `main` siempre debe compilar y pasar tests.
- Conflictos: hablar primero, resolver juntos en una llamada/sesión, probar tras resolver.
- Si un push es rechazado (el remoto avanzó): `git pull --rebase`, resolver, volver a probar, push de nuevo. Nunca `--force` en `main`.

## Cómo evitar pisarse

- Una tarea = una rama = una persona (o avisar antes de tocar rama ajena).
- No editar los mismos archivos a la vez sin coordinar (voz/audio, conversación y config son zonas calientes).
- Comunicar cambios importantes: entrada corta en el log del vault (`ZIXVault/log.md`).
- No borrar código ajeno; no sobrescribir trabajo sin revisar; no asumir que un archivo no se usa.

## Incorporación futura del primo

Todavía NO tiene PC ni cuenta de GitHub: no crear usuario, rama ni accesos. Cuando llegue:

1. Crear cuenta de GitHub.
2. Dar acceso al repositorio (`ZXcris/zix-bot-project`).
3. Instalar Git (https://git-scm.com) y autenticar GitHub (navegador/`gh` o Credential Manager).
4. Clonar ZIX.
5. Instalar Python 3.10+ y dependencias (`pip install -e .`).
6. Copiar `.env.example` a `.env` con su propia `GROQ_API_KEY`.
7. Ejecutar tests (`python -m pytest tests/`).
8. Ejecutar ZIX (`python -m zix.voice_main` con micrófono).
9. Crear su rama (`primo/<tema>`).
10. Trabajar, commit, push, Pull Request, revisión y merge.
