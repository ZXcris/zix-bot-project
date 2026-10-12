import sys

sys.path.insert(0, "/content/openwakeword")
from openwakeword.data import generate_adversarial_texts as g

o = g("hey zix", N=300)
print("CONFUSABLES:", len(o))
for x in o[:8]:
    print("   ", repr(x))
assert len(o) > 50, "deberia generar cientos de confusables"
assert "hey zix" not in o, "PELIGRO: la frase exacta esta entre las negativas"
assert any("zix" in x for x in o), "deberia incluir variantes de zix"
print("PRUEBA_OK")