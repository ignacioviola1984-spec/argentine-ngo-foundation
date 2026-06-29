"""
llm.py  -  La capa de prosa. El UNICO lugar donde el modelo escribe texto.

Tres responsabilidades:

  1. draft(): convierte un payload de hechos deterministicos en una narrativa breve
     en espaniol rioplatense. Si POTENCIAR_USE_LLM=1 y hay API key, Claude la
     escribe; si no, una plantilla deterministica la escribe. En ambos casos el
     resultado pasa por los guardas antes de devolverse.

  2. guarda de grounding numerico (grounding_ok): rechaza cualquier texto que cite
     un NUMERO que no este en el payload permitido. El agente declara exactamente
     que cifras puede mencionar la narrativa; si el modelo inventa una (otro monto,
     un conteo de mas, un anio), el guarda lo frena y draft() cae a la plantilla.
     Prosa sin fundamento numerico nunca se emite.

  3. guarda de PII (pii_ok): rechaza cualquier narrativa que mencione un nombre de
     donante. La PII vive en Salesforce y no sale en una salida que se publica a
     Comision Directiva o donantes; los nombres se quedan atras (capa de gobierno).

Los numeros son deterministicos; la prosa es del modelo. El modelo nunca computa
ni inventa un numero, y nunca expone PII: este modulo hace cumplir ese invariante.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import paths
import governance

try:
    from dotenv import load_dotenv
    load_dotenv(paths.ENV_PATH)
except Exception:
    pass

MODEL = "claude-sonnet-4-6"

# Estilo compartido por toda narrativa (cada agente agrega su especializacion).
STYLE = (
    "Escribis en espaniol rioplatense (Argentina), tono profesional y claro, breve "
    "(2 a 4 frases). Sos el consultor de finanzas escribiendo para la Comision "
    "Directiva y los donantes de una ONG. No inventes datos, numeros, fechas, montos "
    "ni nombres: usa SOLO lo que se te da. No menciones nombres de donantes ni datos "
    "de contacto (son privados, viven en Salesforce). No uses guiones largos (rayas)."
)


def use_llm() -> bool:
    """True solo cuando se activa explicitamente Y hay key. Por defecto: offline
    (plantillas deterministicas), asi el pipeline corre gratis, rapido y reproducible."""
    return os.environ.get("POTENCIAR_USE_LLM") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client


def _call(system, prompt, max_tokens):
    resp = _get_client().messages.create(
        model=MODEL, max_tokens=max_tokens,
        system=system + "\n\n" + STYLE,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# --------------------------------------------------------------------------
# Guarda de grounding (numerico).
# --------------------------------------------------------------------------
_NUM_TOKEN = re.compile(r"\d[\d.,]*")


def _norm_num(token: str) -> str:
    """Normaliza un token numerico a digitos puros (saca . y , y separadores
    sobrantes), asi '50.000', '50,000' y '50000' matchean."""
    return token.strip(".,").replace(".", "").replace(",", "")


def numbers_in(text: str):
    return {_norm_num(t) for t in _NUM_TOKEN.findall(text) if _norm_num(t)}


def allowed_forms(value):
    """Formas de digit-string que un valor permitido puede tomar legitimamente."""
    forms = set()
    if isinstance(value, bool):
        return forms
    if isinstance(value, (int, float)):
        forms.add(_norm_num(str(int(round(value)))))     # forma entera: 50000
        forms.add(_norm_num(("%g" % value)))             # forma compacta: 24.32 -> 2432
        if isinstance(value, float):
            forms.add(_norm_num("%.1f" % value))         # forma un decimal: 4.0 -> '40', 6.3 -> '63'
    else:
        for t in _NUM_TOKEN.findall(str(value)):
            n = _norm_num(t)
            if n:
                forms.add(n)
    return {f for f in forms if f}


def build_allowed(values):
    allowed = set()
    for v in values:
        allowed |= allowed_forms(v)
    return allowed


def grounding_ok(text, allowed_values):
    """(ok, offending): ok es False si el texto cita un numero que no esta en el
    payload permitido. `allowed_values` es la lista de cifras que la narrativa puede
    referenciar."""
    allowed = build_allowed(allowed_values)
    offending = sorted(n for n in numbers_in(text) if n not in allowed)
    return (not offending), offending


def pii_ok(text, pii_terms):
    """(ok, offending): ok es False si el texto menciona un nombre de donante u
    otro termino PII. La PII nunca sale en una narrativa publicable."""
    offending = sorted({t for t in (pii_terms or []) if t and t.lower() in (text or "").lower()})
    return (not offending), offending


# --------------------------------------------------------------------------
# draft(): la unica llamada que hacen los agentes.
# --------------------------------------------------------------------------

def draft(system, prompt, *, allowed_numbers, fallback, pii_terms=None, max_tokens=400):
    """Devuelve una narrativa en espaniol, fundamentada y sin PII.

    allowed_numbers: las cifras que la narrativa puede citar (todo lo demas lo
        rechaza el guarda numerico).
    pii_terms: nombres/datos de donantes que NO pueden aparecer (guarda PII).
    fallback: una plantilla deterministica (armada con el mismo payload) que se usa
        offline O cuando el texto del modelo falla algun guarda.
    """
    source = "template"
    text = fallback
    if use_llm():
        try:
            candidate = _call(system, prompt, max_tokens)
            num_ok, _ = grounding_ok(candidate, allowed_numbers)
            p_ok, _ = pii_ok(candidate, pii_terms)
            if num_ok and p_ok:
                text, source = candidate, "llm"
            else:
                source = "template_guarded"   # el modelo invento una cifra o filtro PII -> rechazado
        except Exception:
            source = "template_error"          # hipo de la API -> nunca rompe la corrida
    return {"text": text, "source": source}
