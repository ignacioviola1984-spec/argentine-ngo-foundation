"""
reporte_agent.py  -  Etapa 5 (construida): reporte a Comision Directiva y donantes.

El artefacto que sale hacia afuera: ejecucion por proyecto y fondo, composicion del
gasto (programa contra administracion), uso de fondos restringidos y de donde
proviene el fondeo. Aplica a los tres niveles de dato, adaptando el contenido a lo
disponible.

Es `publicable`: ademas de la firma de etapa (nivel 1), pasa por el gate final de
publicacion (nivel 2) antes de salir. La PII (nombres de donantes) nunca aparece en
la narrativa: el guarda de PII de llm.py lo hace cumplir.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_base as ab
import finance_core_potenciar as fc

AGENTE = "reporte_agent"
CLAVE = "reporte"


def run(d, ctx, periodo):
    o = d["ong"]
    tier = d["tier"]
    has_contable = tier in ("A", "B")
    has_fondeo = tier in ("A", "C")

    # Gates deterministicos aplicables al nivel de dato de la ONG.
    gates = fc.gates_aplicables(d)

    datos, allowed, partes_detalle = {}, [], []
    if has_contable:
        rpa = int(round(fc.ratio_programa_admin(d) * 100))
        media = int(round(sum(f["ejecucion_pct"] for f in fc.ejecucion_fondos(d)) / len(d["fondos"]) * 100))
        datos.update({"pct_programa": rpa, "ejecucion_media_pct": media})
        allowed += [rpa, media]
        partes_detalle.append(f"{rpa}% a programa · ejecucion media {media}%")
    if has_fondeo:
        n_don = len(d["donantes"])
        conc = int(round(fc.concentracion_donantes(d) * 100))
        datos.update({"donantes_activos": n_don, "concentracion_top3_pct": conc})
        allowed += [n_don, conc]
        partes_detalle.append(f"{n_don} donantes · top-3 {conc}%")
    if d["grant_usd"]:
        consolidado = round(d["grant_usd"] * fc.FX_CIERRE["USD"])
        datos.update({"grant_usd": d["grant_usd"], "grant_consolidado_ars": consolidado})
        allowed += [d["grant_usd"], consolidado, ab.format_ars(consolidado)]

    detalle = " · ".join(partes_detalle) or "Reporte de fondeo (sin dato contable)"
    fallback = fc.narrativa_reporte(d)
    pii_terms = [x["donante"] for x in d["donantes"]] if has_fondeo else []

    prompt = (f"Nivel de dato: {tier}. " + " ".join(f"{k}={v}" for k, v in datos.items() if not str(k).startswith("_"))
              + ". Escribi el reporte a Comision Directiva y donantes. No menciones nombres de donantes.")

    ctx.put(AGENTE, {"tier": tier, **datos})
    return ab.emit_deliverable(
        ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
        detalle=detalle, datos=datos, gates=gates, user_prompt=prompt,
        allowed_numbers=allowed, fallback=fallback, pii_terms=pii_terms, publicable=True)
