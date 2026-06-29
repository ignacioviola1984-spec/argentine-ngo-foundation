"""
agent_base.py  -  Andamiaje compartido de los agentes de etapa.

Cada agente sigue la misma forma: lee los numeros deterministicos de
finance_core_potenciar -> arma los gates (controles) deterministicos -> el modelo
(o la plantilla) redacta la narrativa en espaniol -> la somete como entregable
`pendiente` a la bandeja. Este modulo tiene las piezas compartidas asi cada
archivo de agente queda enfocado en su etapa y su prompt.

Nada de aca computa un numero de dominio: los numeros vienen de finance_core; el
modelo solo narra, y siempre pasando por los guardas de llm.py.

El prompt de cada agente se carga del registro de activos de IA (ai_assets/),
versionado: es lo que se reutiliza al escalar a otra ONG.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import llm
import review
import schema
import paths


def format_ars(x) -> str:
    """Pesos argentinos: separador de miles con punto. 49850 -> '$ 49.850'."""
    return "$ " + f"{int(round(float(x))):,}".replace(",", ".")


# --------------------------------------------------------------------------
# Registro de activos de IA: prompts versionados (ai_assets/prompts.json).
# --------------------------------------------------------------------------
_PROMPTS = None


def _load_prompts():
    global _PROMPTS
    if _PROMPTS is None:
        with open(os.path.join(paths.AI_ASSETS_DIR, "prompts.json"), encoding="utf-8") as f:
            _PROMPTS = json.load(f)
    return _PROMPTS


def prompt_asset(agente: str):
    """Devuelve (system, version) del prompt versionado del agente. Si el registro
    no tiene el agente, devuelve un system generico y version '0' (nunca rompe)."""
    p = _load_prompts().get(agente)
    if not p:
        return ("Sos un agente de finanzas de una ONG. Redactas una narrativa breve "
                "sobre los numeros que se te dan.", "0")
    return p["system"], p["version"]


# --------------------------------------------------------------------------
# emit_deliverable: la unica llamada que hacen los agentes para producir salida.
# --------------------------------------------------------------------------

def emit_deliverable(ctx, *, clave, ong_id, ong_nombre, periodo, tier,
                     detalle, datos, gates, user_prompt, allowed_numbers,
                     fallback, pii_terms=None, publicable=False):
    """Redacta la narrativa (guarda numerico + guarda PII), arma el Deliverable y lo
    somete a la bandeja como pendiente (o bloqueado si un gate falla). Devuelve el dict."""
    etapa = schema.ETAPAS_POR_CLAVE[clave]
    system, version = prompt_asset(etapa["agente"])
    drafted = llm.draft(system, user_prompt, allowed_numbers=allowed_numbers,
                        fallback=fallback, pii_terms=pii_terms)
    dlv = review.Deliverable(
        id=review.make_id(clave, ong_id, periodo),
        etapa_n=etapa["n"], clave=clave, titulo=etapa["titulo"], fase=etapa["fase"],
        agente=etapa["agente"], ong_id=ong_id, ong_nombre=ong_nombre, periodo=periodo,
        tier=tier, detalle=detalle, datos=datos, gates=[list(g) for g in gates],
        narrativa_propuesta=drafted["text"], publicable=publicable,
    )
    # Registra de donde salio la narrativa (llm / template / guarded) y el prompt
    # versionado que la produjo, asi la traza nunca pasa una plantilla por texto del
    # modelo y el activo de IA usado queda asentado.
    dlv.datos = {**datos, "_narrativa_source": drafted["source"],
                 "_prompt_version": version,
                 "_allowed_numbers": [str(n) for n in allowed_numbers]}
    review.add_deliverable(ctx, dlv)
    return dlv.to_dict()


def emit_no_aplica(ctx, *, clave, ong_id, ong_nombre, periodo, tier, motivo):
    """Somete un entregable `no_aplica`: el nivel de dato de la ONG no habilita esta
    etapa. Es la honestidad de cobertura: indicadores parciales, nunca un numero
    inventado para tapar un sistema que falta."""
    etapa = schema.ETAPAS_POR_CLAVE[clave]
    dlv = review.Deliverable(
        id=review.make_id(clave, ong_id, periodo),
        etapa_n=etapa["n"], clave=clave, titulo=etapa["titulo"], fase=etapa["fase"],
        agente=etapa["agente"], ong_id=ong_id, ong_nombre=ong_nombre, periodo=periodo,
        tier=tier, detalle=motivo, datos={"motivo": motivo}, gates=[],
        narrativa_propuesta="", estado=review.NO_APLICA,
    )
    ctx.state["inbox"].append(dlv.to_dict())
    ctx.audit(etapa["agente"], "NO_APLICA", f"etapa {etapa['n']} · {etapa['titulo']} · {motivo}")
    return dlv.to_dict()
