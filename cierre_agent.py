"""
cierre_agent.py  -  Etapa 3 (construida): cierre mensual.

Conciliaciones, devengados (AP con aging), gasto por fondo y plan vs real. Es
fail-closed: si un control deterministico no cuadra, el entregable nace bloqueado y
el cierre no se publica hasta corregir el dato. Requiere dato contable (NetSuite);
una ONG solo en Salesforce no recibe esta etapa (no_aplica).

Los numeros los calcula finance_core_potenciar; el agente arma los gates y redacta.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_base as ab
import finance_core_potenciar as fc

AGENTE = "cierre_agent"
CLAVE = "cierre"


def run(d, ctx, periodo):
    o = d["ong"]
    tier = d["tier"]

    if tier not in ("A", "B"):
        return ab.emit_no_aplica(
            ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
            motivo="Sin dato contable (solo Salesforce): no hay cierre mensual. Requiere NetSuite.")

    ej = fc.ejecucion_fondos(d)
    tot_pres = sum(f["presupuesto"] for f in ej)
    tot_ejec = sum(f["ejecutado"] for f in ej)
    desvio = tot_ejec - tot_pres
    ap_total = sum(d["ap"].values())
    ap_60 = d["ap"]["mas_60"]

    # Conciliaciones de cierre (fail-closed), aplicables al nivel de dato.
    gates = fc.gates_aplicables(d)
    cuadra = all(ok for _, ok in gates)
    detalle = (f"Gasto del periodo {ab.format_ars(tot_ejec)} · desvio plan vs real "
               f"{ab.format_ars(desvio)} · devengado pendiente {ab.format_ars(ap_total)}")
    if cuadra:
        fallback = (f"El cierre concilia: el gasto del periodo por fondo es {ab.format_ars(tot_ejec)} "
                    f"sobre un presupuesto de {ab.format_ars(tot_pres)} (desvio {ab.format_ars(desvio)}). "
                    f"El devengado pendiente de pago es {ab.format_ars(ap_total)}, de los cuales "
                    f"{ab.format_ars(ap_60)} estan vencidos a mas de 60 dias. Las conciliaciones cuadran.")
    else:
        fallback = ("El cierre queda bloqueado: un control deterministico no cuadra (fail-closed). "
                    "No se publica hasta corregir el dato.")

    datos = {"total_presupuesto": tot_pres, "total_ejecutado": tot_ejec,
             "desvio": desvio, "ap_total": ap_total, "ap_mas_60": ap_60}
    allowed = [tot_pres, ab.format_ars(tot_pres), tot_ejec, ab.format_ars(tot_ejec),
               desvio, ab.format_ars(desvio), ap_total, ab.format_ars(ap_total),
               ap_60, ab.format_ars(ap_60)]

    ctx.put(AGENTE, {"tier": tier, "total_ejecutado": tot_ejec, "cuadra": cuadra})
    if not cuadra:
        ctx.flag(AGENTE, "ALTO", "Cierre bloqueado: un control de conciliacion no cuadra (fail-closed).")

    prompt = (f"Gasto del periodo: {ab.format_ars(tot_ejec)}. Presupuesto: {ab.format_ars(tot_pres)}. "
              f"Desvio: {ab.format_ars(desvio)}. Devengado pendiente: {ab.format_ars(ap_total)}. "
              f"Conciliaciones cuadran: {'si' if cuadra else 'no'}. Escribi el resumen del cierre.")
    return ab.emit_deliverable(
        ctx, clave=CLAVE, ong_id=o["id"], ong_nombre=o["nombre"], periodo=periodo, tier=tier,
        detalle=detalle, datos=datos, gates=gates, user_prompt=prompt,
        allowed_numbers=allowed, fallback=fallback)
