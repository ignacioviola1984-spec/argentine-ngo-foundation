"""
dashboards_agent.py  -  Etapa 6 (construida): dashboards por audiencia.

Tres tableros sobre los MISMOS numeros ya conciliados del cierre y el reporte:
Comision Directiva (estrategico), donantes (rendicion) y direccion (operativo). No
introduce numeros nuevos: lee lo que dejaron los agentes anteriores en el estado
compartido. Aplica a los tres niveles de dato, adaptando que tableros tienen datos.

Los graficos los dibuja la app; este agente produce el entregable (titulares +
referencias a las metricas que alimentan cada tablero).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_base as ab
import finance_core_potenciar as fc

AGENTE = "dashboards_agent"
CLAVE = "dashboards"


def run(d, ctx, periodo):
    o = d["ong"]
    tier = d["tier"]
    has_contable = tier in ("A", "B")
    has_fondeo = tier in ("A", "C")

    datos, allowed, titulares = {}, [], []
    if has_contable:
        # Lee el runway que dejo el forecast (misma fuente); si no, lo deriva igual.
        rw = ctx.get("forecast_caja_agent", "runway_meses")
        if rw is None:
            rw = round((fc.runway_meses(d) if tier == "A" else d["caja"] / d["gasto_mensual"]), 1)
        pct_prog = int(round(fc.ratio_programa_admin(d) * 100))
        datos.update({"runway_meses": rw, "pct_programa": pct_prog})
        allowed += [rw, f"{rw:.1f}", pct_prog]
        titulares.append(f"CD: runway {rw:.1f} meses, {pct_prog}% a programa")
    n_esc = len(fc.escalaciones(d))
    datos["escalaciones"] = n_esc
    allowed.append(n_esc)
    if has_fondeo:
        n_don = len(d["donantes"])
        datos["donantes_activos"] = n_don
        allowed.append(n_don)
        titulares.append(f"Donantes: {n_don} activos")
    titulares.append(f"Direccion: {n_esc} escalacion(es) del periodo")

    gates = [("Los tableros muestran solo numeros ya conciliados (sin recomputo)", True)]
    detalle = " · ".join(titulares)
    fallback = ("Tableros por audiencia. " + ". ".join(titulares) +
                ". Cada tablero usa los numeros ya conciliados del cierre y el reporte.")

    prompt = ("Titulares de los tableros: " + "; ".join(titulares) +
              ". Escribi el resumen de los dashboards por audiencia.")
    ctx.put(AGENTE, {"tier": tier, **datos})
    return ab.emit_deliverable(
        ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
        detalle=detalle, datos=datos, gates=gates, user_prompt=prompt,
        allowed_numbers=allowed, fallback=fallback)
