"""
diagnostico_agent.py  -  Etapa 0 (prerrequisito): diagnostico de datos.

El prerrequisito del PDF: antes de prometer cualquier entregable, revisa calidad y
estructura del dato en Salesforce (fondeo) y NetSuite (contable). Determina el
nivel de dato de la ONG (que sistemas estan conectados), que etapas se habilitan y
cuales quedan fuera de alcance. Es el gate que evita prometer un numero que el dato
no soporta.

Los chequeos son deterministicos; el modelo solo redacta el resumen.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_base as ab
import schema

AGENTE = "diagnostico_agent"
CLAVE = "diagnostico"


def run(d, ctx, periodo):
    o = d["ong"]
    tier = d["tier"]
    mp = schema.mapping_ong(o["id"])
    has_contable = tier in ("A", "B")
    has_fondeo = tier in ("A", "C")
    n_sistemas = len(mp["sistemas_conectados"])

    habilitadas = [e["titulo"] for e in schema.ETAPAS_ASISTIDAS if schema.etapa_aplica(e["clave"], tier)]
    fuera = [e["titulo"] for e in schema.ETAPAS_ASISTIDAS if not schema.etapa_aplica(e["clave"], tier)]
    completitud = {"A": 100, "B": 60, "C": 50}[tier]

    # Gates de calidad de dato sobre los sistemas QUE estan conectados (con dato
    # sintetico limpio: pasan). En vivo, aca caen los problemas de etiquetado.
    gates = [("Segregacion por ONG sostenida en cada conexion (solo lectura)", True)]
    if has_contable:
        gates.append(("Plan de cuentas y etiquetado por fondo presentes en NetSuite", True))
    if has_fondeo:
        gates.append(("Donaciones etiquetadas por proyecto/campania en Salesforce", True))

    sistemas_txt = " + ".join(s.capitalize() for s in mp["sistemas_conectados"]) or "ninguno"
    detalle = (f"Nivel de dato: {mp['nivel_dato']} · {n_sistemas} sistema(s) conectado(s) "
               f"({sistemas_txt}) · habilita {len(habilitadas)} de {len(schema.ETAPAS_ASISTIDAS)} etapas asistidas")

    falta = []
    if not has_contable:
        falta.append("NetSuite (contable)")
    if not has_fondeo:
        falta.append("Salesforce (fondeo)")
    falta_txt = (" Queda fuera de alcance lo que requiere " + " y ".join(falta) + ".") if falta else \
        " Set de dato completo: habilita todas las etapas del operating model."
    fallback = (f"El diagnostico de datos da nivel {tier} ({mp['nivel_dato']}). "
                f"Con {n_sistemas} sistema(s) conectado(s) se habilitan {len(habilitadas)} etapas "
                f"de {len(schema.ETAPAS_ASISTIDAS)}.{falta_txt}")

    prompt = (f"Nivel de dato: {mp['nivel_dato']}. Sistemas conectados: {n_sistemas} ({sistemas_txt}). "
              f"Etapas habilitadas: {len(habilitadas)} de {len(schema.ETAPAS_ASISTIDAS)}. "
              f"Fuera de alcance: {', '.join(falta) or 'ninguno'}. Escribi el resumen del diagnostico.")

    ctx.put(AGENTE, {"tier": tier, "n_sistemas": n_sistemas,
                     "habilitadas": habilitadas, "fuera_de_alcance": fuera,
                     "completitud": completitud})
    if fuera:
        ctx.flag(AGENTE, "MEDIO",
                 f"Cobertura parcial: {len(fuera)} etapa(s) fuera de alcance por falta de {' y '.join(falta)}.")

    return ab.emit_deliverable(
        ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
        detalle=detalle,
        datos={"tier": tier, "n_sistemas": n_sistemas,
               "etapas_habilitadas": len(habilitadas),
               "etapas_totales": len(schema.ETAPAS_ASISTIDAS),
               "completitud_pct": completitud},
        gates=gates, user_prompt=prompt,
        allowed_numbers=[n_sistemas, len(habilitadas), len(schema.ETAPAS_ASISTIDAS), completitud, tier],
        fallback=fallback,
    )
