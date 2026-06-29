"""
forecast_caja_agent.py  -  Etapa 4 (construida): forecast de caja y runway.

Proyeccion semanal a 13 semanas cruzando el timing de donaciones (Salesforce) con
los pagos (NetSuite), y el runway en meses de caja. Una ONG con ambos sistemas (A)
recibe el forecast completo; una con solo NetSuite (B) recibe el runway estimado
desde la posicion de caja (indicador parcial, honesto); una con solo Salesforce (C)
no recibe esta etapa (no_aplica).

Los numeros los calcula finance_core_potenciar; el agente arma los gates y redacta.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_base as ab
import finance_core_potenciar as fc

AGENTE = "forecast_caja_agent"
CLAVE = "forecast"


def run(d, ctx, periodo):
    o = d["ong"]
    tier = d["tier"]

    if tier not in ("A", "B"):
        return ab.emit_no_aplica(
            ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
            motivo="Sin dato contable (solo Salesforce): no hay forecast de caja ni runway. Requiere NetSuite.")

    if tier == "A":
        rw = fc.runway_meses(d)
        fcs = fc.forecast_caja_semanal(d)
        saldo_min = min(f["saldo_proyectado"] for f in fcs)
        # Gate con sentido: el saldo proyectado no se vuelve negativo en el horizonte.
        # La caja inicial se concilia (se CALCULA) contra la posicion que reporta NetSuite.
        caja_concilia = d["caja"] == d.get("posicion_caja_netsuite", d["caja"])
        gates = [("Saldo proyectado no se vuelve negativo en 13 semanas", saldo_min >= 0),
                 ("Caja inicial concilia con la posicion de NetSuite", caja_concilia)]
        detalle = (f"Runway {rw:.1f} meses · saldo minimo proyectado {ab.format_ars(saldo_min)} "
                   f"en el horizonte de 13 semanas")
        fallback = fc.narrativa_caja(d)
        datos = {"runway_meses": round(rw, 1), "saldo_minimo": saldo_min,
                 "caja": d["caja"], "semanas": 13}
        allowed = [round(rw, 1), f"{rw:.1f}", saldo_min, ab.format_ars(saldo_min),
                   d["caja"], ab.format_ars(d["caja"]), 13]
    else:  # tier B
        rw = d["caja"] / d["gasto_mensual"]
        saldo_min = d["caja"]
        gates = [("Caja corriente positiva en NetSuite", d["caja"] > 0)]
        detalle = (f"Runway estimado {rw:.1f} meses (solo caja, sin timing de donaciones de Salesforce)")
        fallback = (f"Esta ONG esta solo en NetSuite: se estima un runway de {rw:.1f} meses desde la "
                    f"posicion de caja de {ab.format_ars(d['caja'])}. El forecast semanal completo "
                    f"requiere el timing de donaciones de Salesforce. Es un indicador parcial.")
        datos = {"runway_meses": round(rw, 1), "caja": d["caja"], "parcial": True}
        allowed = [round(rw, 1), f"{rw:.1f}", d["caja"], ab.format_ars(d["caja"])]

    ctx.put(AGENTE, {"runway_meses": round(rw, 1), "tier": tier})
    if rw < fc.RUNWAY_CRITICO:
        ctx.flag(AGENTE, "CRITICO", f"Runway de {rw:.1f} meses, por debajo del umbral de {fc.RUNWAY_CRITICO:.0f}.")
    elif rw < fc.RUNWAY_ALERTA:
        ctx.flag(AGENTE, "ALTO", f"Runway de {rw:.1f} meses, en zona de alerta.")

    prompt = (f"Runway: {rw:.1f} meses. Saldo minimo proyectado: {ab.format_ars(saldo_min)}. "
              f"Nivel de dato: {tier}. Escribi el resumen de liquidez.")
    return ab.emit_deliverable(
        ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
        detalle=detalle, datos=datos, gates=gates, user_prompt=prompt,
        allowed_numbers=allowed, fallback=fallback)
