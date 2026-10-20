#!/bin/bash
# Reentrenamiento zix.onnx con voz real del usuario.
# Cadena reconstruida de las celdas que YA funcionaron en el notebook de Colab,
# mas la inyeccion de los 27 clips reales con sobremuestreo.
# Idempotente: se puede relanzar sin romper nada.
set -u
cd /content

VENV=/content/zixenv
PY=$VENV/bin/python
PIP=$VENV/bin/pip
LOGF=/content/zix_run.log

say() { echo "[$(date +%H:%M:%S)] $*"; }
step() { say ""; say "########## $* ##########"; }
die() { say "FALLO: $*"; exit 1; }

# ---------- 1. python3.10 + venv ----------
step "1. python3.10 y venv"
if ! command -v python3.10 >/dev/null 2>&1; then
  sudo apt-get update -qq >/dev/null 2>&1
  sudo apt-get install -y -qq python3.10 python3.10-venv >/dev/null 2>&1
fi
python3.10 --version || die "no hay python3.10"
if [ ! -x "$PY" ]; then
  python3.10 -m venv /content/zixenv || die "venv fallo"
fi
"$PY" --version

step "2. pip y torch cu121"
"$PIP" install -q --upgrade pip 2>&1 | tail -1
"$PIP" install -q --retries 5 --timeout 180 torch torchaudio \
  --index-url https://download.pytorch.org/whl/cu121 2>&1 | tail -2
"$PY" -c 'import torch; print("CUDA=", torch.cuda.is_available(), torch.__version__)'

step "3. deps menores"
"$PIP" install -q --retries 5 --timeout 180 soundfile piper-phonemize \
  webrtcvad-wheels mutagen pronouncing scipy 2>&1 | tail -3
"$PY" -c 'import soundfile, piper_phonemize, webrtcvad; print("SMALL_OK")'

step "4. piper-tts (antes de parchear: aporta el paquete dp)"
"$PIP" install -q --retries 5 --timeout 300 piper-tts 2>&1 | tail -3
"$PY" -c 'from piper import PiperVoice; print("PIPER_TTS_OK")' || die "piper-tts no importa"

step "5. deps mayores"
"$PIP" install -q --retries 5 --timeout 300 numpy==1.26.4 pyarrow==13.0.0 \
  datasets==2.14.6 torchinfo==1.8.0 torchmetrics==1.2.0 speechbrain==0.5.14 \
  audiomentations==0.33.0 acoustics==0.2.6 deep-phonemizer==0.0.19 \
  onnxruntime onnxscript onnx ai-edge-litert 2>&1 | tail -3
"$PY" -c 'import numpy, datasets, speechbrain, onnxruntime, onnxscript; print("BIG_OK", numpy.__version__)'

step "6. repos"
[ -d /content/piper-sample-generator ] || git clone -q https://github.com/rhasspy/piper-sample-generator
cd /content/piper-sample-generator && git checkout -q v2.0.0 && cd /content
[ -d /content/openwakeword ] || git clone -q https://github.com/dscripka/openwakeword
"$PIP" install -q --no-deps -e /content/openwakeword 2>&1 | tail -2
"$PY" -c 'import openwakeword; print("REPOS_OK")'

step "7. parche 1: torch.load weights_only (piper + dp)"
cat > /content/apply_patches.py <<'PYEOF'
import pathlib, re

p1 = pathlib.Path('/content/piper-sample-generator/generate_samples.py')
t1 = p1.read_text()
t1 = t1.replace('torch.load(model_path)', 'torch.load(model_path, weights_only=False)')
p1.write_text(t1)
print('patch piper OK')

p2 = pathlib.Path('/content/zixenv/lib/python3.10/site-packages/dp/model/model.py')
if p2.exists():
    t2 = p2.read_text()
    t2n, n = re.subn(r'torch\.load\(([^)]+)\)', r'torch.load(\1, weights_only=False)', t2)
    p2.write_text(t2n)
    print(f'patch dp OK ({n} subs)')
else:
    print('AVISO: dp/model/model.py no existe, parche omitido')
PYEOF
"$PY" /content/apply_patches.py || die "apply_patches fallo"

step "8. torch-audiomentations + parche 2 (torchaudio.info)"
"$PIP" install -q --retries 5 --timeout 300 torch-audiomentations 2>&1 | tail -2
cat > /content/apply_patch3.py <<'PYEOF'
import pathlib
p3 = pathlib.Path('/content/zixenv/lib/python3.10/site-packages/torch_audiomentations/utils/io.py')
if not p3.exists():
    print('AVISO: io.py no encontrado'); raise SystemExit(0)
t3 = p3.read_text()
if "hasattr(torchaudio" not in t3:
    t3 = t3.replace('import torchaudio', "import torchaudio\nif not hasattr(torchaudio, 'info'):\n    import soundfile as _sf\n    def _ti(path):\n        info=_sf.info(path)\n        class _I: pass\n        i=_I(); i.num_frames=info.frames; i.sample_rate=info.samplerate; return i\n    torchaudio.info=_ti")
    p3.write_text(t3)
    print('patch torchaudio.info OK')
else:
    print('patch torchaudio.info ya aplicado')
PYEOF
"$PY" /content/apply_patch3.py || die "apply_patch3 fallo"
"$PY" -c 'import torch_audiomentations; print("TAUDI_OK")'

step "9. parche 3: data.py usa soundfile en vez de torchaudio"
cat > /content/patch_data.py <<'PYEOF'
path = '/content/openwakeword/openwakeword/data.py'
with open(path) as f:
    content = f.read()
if '_load_wav' in content:
    print('data.py ya parcheado'); raise SystemExit(0)
wrapper = '\n'.join([
    'import soundfile as _sfi',
    'import torch as _tch',
    'import numpy as _np',
    '',
    'def _load_wav(path):',
    '    try:',
    '        data, sr = _sfi.read(str(path))',
    '    except Exception:',
    '        import scipy.io.wavfile as _wav',
    '        sr, data = _wav.read(str(path))',
    '    t = _tch.from_numpy(np.asarray(data).astype(np.float32))',
    '    if t.dim() == 1:',
    '        t = t.unsqueeze(0)',
    '    return t, sr',
    '',
    'def _save_wav(path, data, sr):',
    '    if isinstance(data, _tch.Tensor):',
    '        data = data.cpu().numpy()',
    '    _sfi.write(str(path), data, sr)',
    '',
])
lines = content.split('\n')
new_lines, inserted = [], False
for line in lines:
    s = line.strip()
    if not inserted and s and not s.startswith('#') and not s.startswith('import ') and not s.startswith('from '):
        new_lines.append(wrapper); new_lines.append(''); inserted = True
    new_lines.append(line)
content = '\n'.join(new_lines)
content = content.replace('torchaudio.load(', '_load_wav(')
content = content.replace('torchaudio.save(', '_save_wav(')
with open(path, 'w') as f:
    f.write(content)
import py_compile; py_compile.compile(path, doraise=True)
c = open(path).read()
print(f"load_wav={c.count('_load_wav')} ta_load={c.count('torchaudio.load(')} SYNTAX OK")
PYEOF
"$PY" /content/patch_data.py || die "patch_data fallo"

step "10. features precomputadas + voces piper"
[ -f /content/openwakeword_features_ACAV100M_2000_hrs_16bit.npy ] || \
  wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy \
    -O /content/openwakeword_features_ACAV100M_2000_hrs_16bit.npy
[ -f /content/validation_set_features.npy ] || \
  wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy \
    -O /content/validation_set_features.npy
ls -lh /content/*.npy

mkdir -p /content/piper-sample-generator/models
cd /content/piper-sample-generator/models
V=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US
for spk in libritts_r hfc_female hfc_male ryan lessac; do
  [ -f en_US-${spk}-medium.onnx ] || wget -q -O en_US-${spk}-medium.onnx $V/${spk}/medium/en_US-${spk}-medium.onnx
  [ -f en_US-${spk}-medium.onnx.json ] || wget -q -O en_US-${spk}-medium.onnx.json $V/${spk}/medium/en_US-${spk}-medium.onnx.json
done
[ -f en_US-libritts_r-medium.pt ] || wget -q -O en_US-libritts_r-medium.pt \
  https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
ls -lh | tail -15
cd /content

step "11. reverberacion (MIT RIR) y fondo (ESC-50)"
cat > /content/get_rirs.py <<'PYEOF'
import os, datasets, scipy.io.wavfile, numpy as np
from tqdm import tqdm
os.makedirs('/content/mit_rirs', exist_ok=True)
if len([f for f in os.listdir('/content/mit_rirs') if f.endswith('.wav')]) >= 200:
    print('RIRs ya descargados'); raise SystemExit(0)
ds = datasets.load_dataset('davidscripka/MIT_environmental_impulse_responses', split='train', streaming=True)
ds = ds.cast_column('audio', datasets.Audio(sampling_rate=16000))
for i, row in enumerate(tqdm(ds)):
    a = row['audio']
    try:
        path = a['path'].split('/')[-1]; arr = a['array']
    except (TypeError, KeyError):
        path = f'rir_{i:03d}.wav'
        arr = a.get_all_samples().data
        if hasattr(arr, 'numpy'): arr = arr.numpy()
    scipy.io.wavfile.write(os.path.join('/content/mit_rirs', path), 16000, (np.asarray(arr)*32767).astype(np.int16))
    if i >= 269: break
print('RIRs OK', len(os.listdir('/content/mit_rirs')))
PYEOF
"$PY" /content/get_rirs.py

cat > /content/clean_rirs.py <<'PYEOF'
import os, soundfile
good = bad = 0
for f in sorted(os.listdir('/content/mit_rirs')):
    p = '/content/mit_rirs/' + f
    try:
        soundfile.read(p); good += 1
    except Exception:
        os.remove(p); bad += 1
print(f'RIRs: {good} good, {bad} removed')
PYEOF
"$PY" /content/clean_rirs.py

cat > /content/get_background.py <<'PYEOF'
import os, zipfile, random, subprocess
import scipy.io.wavfile, numpy as np
os.makedirs('/content/background', exist_ok=True)
os.makedirs('/content/esc50tmp', exist_ok=True)
n_hay = len([f for f in os.listdir('/content/background') if f.endswith('.wav')])
if n_hay >= 300:
    print('fondo ya descargado'); raise SystemExit(0)
subprocess.run(['wget','-q','https://codeload.github.com/karolpiczak/ESC-50/zip/refs/heads/master','-O','/content/esc50tmp/esc50.zip'])
zf = zipfile.ZipFile('/content/esc50tmp/esc50.zip')
names = [n for n in zf.namelist() if n.endswith('.wav')]
print('wavs en zip:', len(names), flush=True)
random.seed(7)
n = 0
for nm in random.sample(names, min(400, len(names))):
    open('/content/esc50tmp/t.wav','wb').write(zf.read(nm))
    try:
        sr, arr = scipy.io.wavfile.read('/content/esc50tmp/t.wav')
        if arr.ndim > 1: arr = arr.mean(axis=1)
        if sr != 16000:
            idx = np.minimum((np.arange(int(len(arr)*16000/sr))).astype(int), len(arr)-1)
            arr = arr[idx]
        scipy.io.wavfile.write(f'/content/background/bg_{n:04d}.wav', 16000, arr.astype(np.int16))
        n += 1
    except Exception as e:
        print('skip', nm, str(e)[:60], flush=True)
print(f'BACKGROUND OK {n} clips')
PYEOF
"$PY" /content/get_background.py
echo "RIRs=$(ls /content/mit_rirs/*.wav 2>/dev/null | wc -l) fondo=$(ls /content/background/bg_*.wav 2>/dev/null | wc -l)"

step "12. modelos de features (git-lfs: el clone normal trae punteros)"
command -v git-lfs >/dev/null 2>&1 || sudo apt-get install -y -qq git-lfs >/dev/null 2>&1
mkdir -p /content/openwakeword/openwakeword/resources/models
if [ ! -s /content/openwakeword/openwakeword/resources/models/melspectrogram.onnx ]; then
  rm -rf /tmp/owwlfs
  git clone -q https://github.com/dscripka/openWakeWord /tmp/owwlfs
  cd /tmp/owwlfs && git checkout -q 185cda5~1 && git lfs pull 2>&1 | tail -2
  cp /tmp/owwlfs/openwakeword/resources/models/melspectrogram.onnx \
     /tmp/owwlfs/openwakeword/resources/models/embedding_model.onnx \
     /content/openwakeword/openwakeword/resources/models/
  cd /content
fi
"$PY" -c "import onnxruntime as o; o.InferenceSession('/content/openwakeword/openwakeword/resources/models/melspectrogram.onnx'); o.InferenceSession('/content/openwakeword/openwakeword/resources/models/embedding_model.onnx'); print('ORT_LOAD_OK')"

step "13. configuracion my_model.yaml"
cat > /content/write_yaml2.py <<'PYEOF'
import yaml
cfg = {
    'model_name': 'zix',
    'model_type': 'dnn',
    'layer_size': 32,
    'target_phrase': ['hey zix'],
    'negative_phrases': ['hey jarvis', 'hey siri', 'hey google', 'alexa', 'ok google'],
    'output_dir': './zix_model',
    'batch_n_per_class': {'ACAV100M_sample': 1024, 'adversarial_negative': 50, 'positive': 50},
    'n_samples': 5000,
    'n_samples_val': 2000,
    'tts_batch_size': 10,
    'augmentation_batch_size': 32,
    'augmentation_rounds': 1,
    'training_epochs': 30000,
    'learning_rate': 0.001,
    'background_paths': ['./background'],
    'background_paths_duplication_rate': [1],
    'piper_sample_generator_path': '/content/piper-sample-generator',
    'feature_data_files': {'ACAV100M_sample': './openwakeword_features_ACAV100M_2000_hrs_16bit.npy'},
    'rir_paths': ['/content/mit_rirs/'],
    'custom_negative_phrases': [],
    'false_positive_validation_data_path': './validation_set_features.npy',
    'max_negative_weight': 2.0,
    'positive_test_clips_recall': 0.9,
    'target_false_positives_per_hour': 10.0,
    'steps': 30000,
}
with open('/content/my_model.yaml', 'w') as f:
    yaml.dump(cfg, f)
print('YAML V2 OK')
PYEOF
"$PY" /content/write_yaml2.py && ls -lh /content/my_model.yaml

step "14. subir y descomprimir los 27 clips reales"
if [ ! -d /content/hey_zix_real ]; then
  ls /content/*.zip 2>/dev/null || die "no hay ningun zip en /content: sube heyzix_clips.zip al panel Archivos"
  for z in /content/*.zip; do unzip -q -o "$z" -d /content/; done
fi
echo "clips reales: $(ls /content/hey_zix_real/*.wav 2>/dev/null | wc -l)"

step "15. generar clips sinteticos (LENTO ~40 min)"
if [ "$(ls /content/zix_model/zix/positive_train/*.wav 2>/dev/null | wc -l)" -lt 100 ]; then
  MPLBACKEND=Agg "$PY" openwakeword/openwakeword/train.py --training_config my_model.yaml --generate_clips \
    || die "generate_clips fallo"
else
  say "positivos sinteticos ya presentes, se omite"
fi
echo "POSITIVOS_SINTETICOS=$(ls /content/zix_model/zix/positive_train/*.wav 2>/dev/null | wc -l)"

step "16. multivoces (3 voces x 3 velocidades)"
cat > /content/synth_multivoice.py <<'PYEOF'
import os
import scipy.io.wavfile, numpy as np
from scipy.signal import resample_poly
from piper import PiperVoice
from piper.config import SynthesisConfig
OUT_TRAIN = '/content/zix_model/zix/positive_train'
OUT_TEST  = '/content/zix_model/zix/positive_test'
MDIR = '/content/piper-sample-generator/models'
os.makedirs(OUT_TRAIN, exist_ok=True); os.makedirs(OUT_TEST, exist_ok=True)
voices = ['hfc_male', 'hfc_female', 'ryan']
scales = [0.9, 1.0, 1.1]
n_train_each, n_test_each = 300, 100
total = 0
for v in voices:
    if not os.path.exists(f'{MDIR}/en_US-{v}-medium.onnx'):
        print('voz ausente:', v); continue
    voice = PiperVoice.load(f'{MDIR}/en_US-{v}-medium.onnx')
    for split, outdir, n_each in [('tr', OUT_TRAIN, n_train_each), ('te', OUT_TEST, n_test_each)]:
        for i in range(n_each):
            fn = f'{outdir}/mv_{v}_{split}_{i:04d}.wav'
            if os.path.exists(fn):
                total += 1; continue
            ls = scales[(i + len(v)) % 3]
            chunks = []
            for chunk in voice.synthesize('Hey ZIX', syn_config=SynthesisConfig(length_scale=ls)):
                chunks.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32))
            d = np.concatenate(chunks) if chunks else np.zeros(22050, dtype=np.float32)
            scipy.io.wavfile.write(fn, 16000, resample_poly(d, 320, 441).astype(np.int16))
            total += 1
            if total % 200 == 0: print(f'synth {total}...', flush=True)
print(f'MULTIVOICE DONE total={total}')
PYEOF
"$PY" /content/synth_multivoice.py
echo "MV_TRAIN=$(ls /content/zix_model/zix/positive_train/mv_*.wav 2>/dev/null | wc -l) MV_TEST=$(ls /content/zix_model/zix/positive_test/mv_*.wav 2>/dev/null | wc -l)"

step "17. INYECTAR LOS 27 CLIPS REALES con sobremuestreo"
cat > /content/inject_real.py <<'PYEOF'
import glob, os, random, shutil
from pathlib import Path
import numpy as np, scipy.io.wavfile

COPIAS = int(os.environ.get("ZIX_REAL_COPIAS", "100"))
SRC   = Path('/content/hey_zix_real')
POS_TR = Path('/content/zix_model/zix/positive_train')
POS_TE = Path('/content/zix_model/zix/positive_test')
HELD   = Path('/content/zix_real_heldout')

def _leer(ruta):
    sr, data = scipy.io.wavfile.read(str(ruta))
    if data.ndim > 1:
        data = data.mean(axis=1).astype(np.int16)
    if sr != 16000:
        from scipy import signal
        n = int(len(data) * 16000 / sr)
        data = signal.resample(data.astype(np.float32), n)
        data = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    return data

if not SRC.is_dir():
    raise SystemExit("ERROR: no existe /content/hey_zix_real/")
wavs = sorted(SRC.glob('*.wav'))
if not wavs:
    raise SystemExit("ERROR: /content/hey_zix_real/ vacio")

random.seed(7)
n_val = max(1, int(len(wavs) * 0.15))
retenidos = set(random.sample(wavs, n_val))

POS_TR.mkdir(parents=True, exist_ok=True)
HELD.mkdir(parents=True, exist_ok=True)
for viejo in HELD.glob('*.wav'):
    viejo.unlink()
# limpiar copias anteriores de esta inyeccion (idempotencia)
for viejo in POS_TR.glob('real_*_c*.wav'):
    viejo.unlink()

n_train = n_held = saltados = 0
for w in wavs:
    try:
        data = _leer(w)
        dur = len(data) / 16000
        if not (0.5 <= dur <= 5.0):
            print(f"  SKIP {w.name}: duracion {dur:.2f}s"); saltados += 1; continue
        if w in retenidos:
            # retenido: NO entra al entrenamiento. Se usa despues con verify_heldout.py
            scipy.io.wavfile.write(str(HELD / w.name), 16000, data)
            n_held += 1
            continue
        for c in range(COPIAS):
            jitter = 1.0 + random.uniform(-0.03, 0.03)
            ganancia = random.uniform(0.85, 1.10)
            d = np.clip(data.astype(np.float32) * jitter * ganancia, -32768, 32767)
            scipy.io.wavfile.write(str(POS_TR / f"real_{w.stem}_c{c:03d}.wav"), 16000, d.astype(np.int16))
        n_train += 1
    except Exception as e:
        print(f"  SKIP {w.name}: {type(e).__name__}: {e}"); saltados += 1

reales = len(list(POS_TR.glob('real_*_c*.wav')))
total_pos = len(list(POS_TR.glob('*.wav')))
print("")
print(f"  Clips reales en entrenamiento      : {n_train}")
print(f"  COPIAS por clip                    : {COPIAS}")
print(f"  Ficheros reales en positive_train  : {reales}")
print(f"  RETENIDOS (el modelo no los vera)   : {n_held} -> {HELD}")
print(f"  Saltados                           : {saltados}")
if total_pos:
    print(f"  Peso de la voz REAL en los positivos: {100*reales/total_pos:.1f} %")
print("")
print("  Continua con augment_clips y train_model.")
print("  Para verificar de verdad: baja /content/zix_real_heldout y usa verify_heldout.py")
PYEOF
ZIX_REAL_COPIAS="${ZIX_REAL_COPIAS:-100}" "$PY" /content/inject_real.py || die "inyeccion de clips reales fallo"
echo "POSITIVOS_TOTAL=$(ls /content/zix_model/zix/positive_train/*.wav 2>/dev/null | wc -l)"

step "17b. COMPUERTA PRE-ENTRENAMIENTO (falla aqui, no en 40 minutos)"
# ---------------------------------------------------------------------------
# POR QUE: en septiembre la corrida completo hasta el final y solo entonces se
# vio que el modelo no servia. Si la voz real no llega a positive_train, o el
# retenido no existe, no hay nada que verificar despues. Se para ANTES de
# augment (~10 min) y train (~30-60 min).
# EQUIVALE a validar_preflight.py [3][4][6], que corre en local.
# ---------------------------------------------------------------------------
cat > /content/gate_pre.py <<'PYEOF'
import sys, yaml
from pathlib import Path

RAIZ = Path('/content')
POS  = RAIZ/'zix_model/zix/positive_train'
NEG  = RAIZ/'zix_model/zix/negative_train'
HELD = RAIZ/'zix_real_heldout'
cfg  = yaml.safe_load(open('/content/my_model.yaml'))
errores, avisos = [], []

# 1) la frase objetivo NO puede ser negativa
objetivo = {t.lower().strip() for t in cfg.get('negative_phrases', [])} \
         | {t.lower().strip() for t in cfg.get('custom_negative_phrases', [])}
malos = objetivo & {t.lower().strip() for t in cfg.get('target_phrase', [])}
if malos:
    errores.append(f'la frase objetivo {malos} esta en las frases negativas')

# 2) la voz real tiene que estar EN LA CARPETA QUE LEE train.py
reales = list(POS.glob('real_*_c*.wav')) if POS.is_dir() else []
todos  = list(POS.glob('*.wav'))       if POS.is_dir() else []
if not reales:
    errores.append(f'0 clips reales en {POS}: train.py no los leera')
elif not todos:
    errores.append(f'{POS} esta vacia')
else:
    pct = 100*len(reales)/len(todos)
    if pct < 5:
        avisos.append(f'la voz real es solo {pct:.1f}% de los positivos: sube ZIX_REAL_COPIAS')

# 3) sin retenidos no hay verificacion honesta posible
retenidos = list(HELD.glob('*.wav')) if HELD.is_dir() else []
if not retenidos:
    errores.append(f'{HELD} vacio: sin clips retenidos no podras verificar el modelo')

# 4) fuga: ningun retenido puede estar tambien en entrenamiento
tren = {p.name for p in POS.glob('*.wav')} if POS.is_dir() else set()
fuga = tren & {p.name for p in retenidos}
if fuga:
    errores.append(f'FUGA: {sorted(fuga)[:5]} estan en entrenamiento y en retenidos')

print(f'  positivos={len(todos)} reales={len(reales)} retenidos={len(retenidos)}')
for a in avisos:  print(f'  [aviso]   {a}')
for e in errores: print(f'  [CRITICO] {e}')
sys.exit(1 if errores else (2 if avisos else 0))
PYEOF
"$PY" /content/gate_pre.py; GATE=$?
# 0 = todo bien, 2 = avisos, 1 = critico. Solo el 1 detiene la corrida.
if [ "$GATE" -eq 1 ]; then
  die "COMPUERTA PRE: no se va a gastar GPU con estos datos (ver [CRITICO] arriba)"
fi
[ "$GATE" -eq 2 ] && say "COMPUERTA PRE: avisos, se continua"

step "18. augment (LENTO ~10 min)"
# --overwrite regenera el directorio: sin esto el n_total de train.py cuenta
# ficheros de una ejecucion parcial anterior y el generador se agota antes
# -> StopIteration (el fallo real de septiembre, train.py:800 -> utils.py:575).
rm -f /content/zix_model/zix/positive_features_*.npy /content/zix_model/zix/negative_features_*.npy
MPLBACKEND=Agg "$PY" openwakeword/openwakeword/train.py --training_config my_model.yaml \
  --augment_clips --overwrite || die "augment_clips fallo (manda el traceback)"
ls -lh /content/zix_model/zix/*.npy

step "19. ENTRENAR (LENTO ~30-60 min)"
MPLBACKEND=Agg "$PY" openwakeword/openwakeword/train.py --training_config my_model.yaml \
  --train_model --overwrite || die "train_model fallo (manda el traceback)"

step "19b. COMPUERTA POST-ENTRENAMIENTO (el modelo sirve de verdad?)"
# ---------------------------------------------------------------------------
# POR QUE: train_model termina con exito codigo 0 aunque el modelo sea
# inutil. El de septiembreacia asi: recall 3/27 con umbral 0.5. Esta compuerta
# lo mide con el retenido (nunca visto) y con negativos reales, y RECHAZA la
# corrida antes de empaquetar un modelo que no funciona.
# UMBRAL y criterios NO son arbitrarios: recall@0.5 y FAR@0.5 sobre el
# retenido, que es la unica medida honesta disponible.
# ---------------------------------------------------------------------------
cat > /content/gate_post.py <<'PYEOF'
import sys
from pathlib import Path
import numpy as np, scipy.io.wavfile as wav
from openwakeword.model import Model

MODELO = '/content/zix_model/zix_model/zix.onnx'
HELD   = Path('/content/zix_real_heldout')
NEGDIR = Path('/content/zix_model/zix/negative_test')
UMBRAL, B = 0.5, 1280

if not Path(MODELO).is_file():
    print(f'  [CRITICO] no se exporto {MODELO}'); sys.exit(1)

m = Model(wakeword_models=[MODELO], inference_framework='onnx')
k = [x for x in m.models if 'zix' in x][0]

def leer(p):
    sr, d = wav.read(str(p)); x = d.astype(np.float32)
    if x.ndim > 1: x = x.mean(axis=1)
    if sr != 16000:
        from scipy import signal
        x = signal.resample(x, int(len(x)*16000/sr))
    return (np.clip(x, -1, 1)*32767).astype(np.int16)

def maxs(a):
    return max(float(m.predict(a[i:i+B])[k]) for i in range(0, len(a)-B+1, B))

pos = [maxs(leer(p)) for p in sorted(HELD.glob('*.wav'))] if HELD.is_dir() else []
neg = [maxs(leer(p)) for p in sorted(NEGDIR.glob('*.wav'))[:2000]] if NEGDIR.is_dir() else []

print(f'  retenidos n={len(pos)}  max={max(pos) if pos else 0:.4f}  media={np.mean(pos) if pos else 0:.4f}')
print(f'  negativos n={len(neg)}  max={max(neg) if neg else 0:.4f}')
recall = sum(1 for s in pos if s >= UMBRAL)/len(pos) if pos else 0.0
far    = sum(1 for s in neg if s >= UMBRAL)/len(neg) if neg else None

errores = []
if not pos:
    errores.append('no hay retenidos que evaluar')
elif recall < 0.5:
    errores.append(f'recall@{UMBRAL} = {recall:.0%} sobre el retenido: el modelo '
                   f'no reconoce la frase que debe despertar')
if far is not None and far > 0.02:
    errores.append(f'FAR@{UMBRAL} = {far:.2%}: se dispararia continuamente')
for e in errores: print(f'  [CRITICO] {e}')
if not errores: print('  [ok] el modelo pasa la puerta: recall y FAR aceptables')
sys.exit(1 if errores else 0)
PYEOF
"$PY" /content/gate_post.py 2>&1 | tee /content/gate_post.log
if [ "${PIPESTATUS[0]}" -eq 1 ]; then
  say "COMPUERTA POST FALLIDA: se empaqueta igual para no perderlo, pero NO lo instales en ZIX sin reentrenar"
fi
cp -f /content/gate_pre.py /content/gate_post.py /content/zix_artifacts_* 2>/dev/null || true

step "20. resultado + descarga verificable de artefactos"
# ---------------------------------------------------------------------------
# DEFECTO CORREGIDO: antes esto solo listaba los ficheros. Al caducar la
# sesion de Colab se perdia TODO el entrenamiento. Ahora se empaqueta y se
# descarga, y se verifica la integridad de cada artefacto.
# ---------------------------------------------------------------------------
find /content/zix_model -name '*.onnx*' -o -name '*.tflite' | head -20
ls -lh /content/zix_model/zix_model/ 2>/dev/null

STAMP=$(date +%Y%m%d_%H%M%S)
OUTDIR=/content/zix_artifacts_$STAMP
mkdir -p "$OUTDIR"

# 1) modelo final (el que se baja y se usa)
for f in /content/zix_model/zix_model/*.onnx; do
  [ -e "$f" ] || continue
  cp "$f" "$OUTDIR/"
done
# 2) retenidos: SIN esto no hay validacion honesta posible
if [ -d /content/zix_real_heldout ]; then
  cp -r /content/zix_real_heldout "$OUTDIR/"
fi
# 3) negativos generados (trazabilidad de los datos)
if [ -d /content/zix_model/zix/negative_train ]; then
  tar -czf "$OUTDIR/negative_train.tar.gz" -C /content/zix_model/zix negative_train
fi
# 4) config y log de la corrida
cp /content/my_model.yaml "$OUTDIR/" 2>/dev/null || true
cp /content/zix_run.log "$OUTDIR/" 2>/dev/null || true

# 5) manifiesto con SHA256 de cada artefacto -> la descarga se puede verificar
( cd "$OUTDIR" && find . -type f ! -name MANIFESTO_SHA256.txt -print0 \
    | sort -z | xargs -0 sha256sum > MANIFESTO_SHA256.txt )
echo "--- MANIFESTO_SHA256 ---"
cat "$OUTDIR/MANIFESTO_SHA256.txt"
echo "----------------------"

tar -czf /content/zix_artifacts.tar.gz -C "$OUTDIR" .
ls -lh /content/zix_artifacts.tar.gz

# 6) descarga automatica. Si falla, el tar queda en /content para recuperarlo
#    a mano antes de que caduque la sesion.
if command -v gdown >/dev/null 2>&1; then
  gdown --no-cookies "/content/zix_artifacts.tar.gz" 2>/dev/null \
    || say "AVISO: gdown no pudo descargar; baja /content/zix_artifacts.tar.gz a mano"
else
  say "AVISO: gdown no instalado. Baja /content/zix_artifacts.tar.gz a mano ANTES de que caduque la sesion"
fi

say "PIPELINE COMPLETO"
say "ARTEFACTOS en: $OUTDIR  y  /content/zix_artifacts.tar.gz"