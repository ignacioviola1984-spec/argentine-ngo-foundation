"""
potenciar_orchestrator.py  -  La capa de orquestacion (Cowork) del operating model.

Espeja cfo_orchestrator / nexo_orchestrator para el dominio de la ONG:

  lee las dos fuentes (NetSuite + Salesforce, solo lectura) -> corre los agentes de
  etapa sobre un PotenciarContext compartido -> cross-checks deterministicos (los
  entregables reconcilian con el motor de numeros) -> bandeja de entregables en el
  orden del operating model -> gate HITL de dos niveles (firma por etapa + gate
  final de publicacion) -> traza de auditoria + persistencia.

Conecta las dos fuentes que hoy no se hablan (Salesforce y NetSuite), cruza los
datos, corre los controles y genera las salidas y el rastro de auditoria. Los
numeros vienen de finance_core_potenciar; el modelo solo narra.

  python potenciar_orchestrator.py                          # gate HITL interactivo
  POTENCIAR_AUTO_APPROVE=1 python potenciar_orchestrator.py # auto-firma (CI/replay)
  POTENCIAR_USE_LLM=1 python potenciar_orchestrator.py      # usa Claude para la prosa
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import finance_core_potenciar as fc
import governance
import review
import schema
from shared_state import PotenciarContext
import diagnostico_agent
import forecast_caja_agent
import reporte_agent
import cierre_agent
import dashboards_agent


def _auto() -> bool:
    """Auto-firma cuando se activa o cuando no hay humano en la consola (CI, pipes,
    replay), asi la corrida nunca cuelga."""
    if os.environ.get("POTENCIAR_AUTO_APPROVE") == "1":
        return True
    try:
        return not sys.stdin.isatty()
    except (AttributeError, ValueError):
        return True


# --------------------------------------------------------------------------
# Cross-checks deterministicos: los entregables reconcilian con el motor.
# Si un agente deriva distinto de la unica fuente de numeros, salta aca y no en la
# salida (misma idea que el cross_checks del CFO / Nexo).
# --------------------------------------------------------------------------

def cross_checks(ctx, d):
    issues = []
    tier = d["tier"]

    # 1) una etapa == un entregable (incluido el diagnostico); el total coincide.
    if len(ctx.state["inbox"]) != len(schema.ETAPAS):
        issues.append(f"inbox {len(ctx.state['inbox'])} != etapas {len(schema.ETAPAS)}")
    for e in schema.ETAPAS:
        dlv = review.get(ctx, e["clave"])
        if dlv is None:
            issues.append(f"falta el entregable de la etapa {e['clave']}")
            continue
        aplica = schema.etapa_aplica(e["clave"], tier)
        if not aplica and dlv["estado"] != review.NO_APLICA:
            issues.append(f"{e['clave']}: deberia ser no_aplica para tier {tier}")
        if aplica and dlv["estado"] == review.NO_APLICA:
            issues.append(f"{e['clave']}: marcado no_aplica pero aplica a tier {tier}")

    # 2) consistencia bloqueado <-> gate en False.
    for dlv in ctx.state["inbox"]:
        if dlv["estado"] == review.NO_APLICA:
            continue
        gate_falla = any(not ok for _, ok in dlv["gates"])
        if gate_falla and dlv["estado"] != review.BLOQUEADO:
            issues.append(f"{dlv['clave']}: un gate falla pero no esta bloqueado")
        if dlv["estado"] == review.BLOQUEADO and not gate_falla:
            issues.append(f"{dlv['clave']}: bloqueado sin gate que falle")

    # 3) el runway del forecast coincide con el de dashboards (misma fuente).
    fc_rw = ctx.get("forecast_caja_agent", "runway_meses")
    db_rw = ctx.get("dashboards_agent", "runway_meses")
    if fc_rw is not None and db_rw is not None and fc_rw != db_rw:
        issues.append(f"runway forecast {fc_rw} != dashboards {db_rw}")

    # 4) el ejecutado del cierre reconcilia con la suma de fondos del motor.
    if tier in ("A", "B"):
        esperado = sum(f["ejecutado"] for f in fc.ejecucion_fondos(d))
        cierre_ejec = ctx.get("cierre_agent", "total_ejecutado")
        if cierre_ejec is not None and cierre_ejec != esperado:
            issues.append(f"cierre ejecutado {cierre_ejec} != suma de fondos {esperado}")

    # 5) el join de la orquestacion coincide con el gate cross-sistema del reporte.
    if tier == "A":
        rec = fc.reconciliacion_fondeo(d)
        rep = review.get(ctx, "reporte")
        if rec is not None and rep is not None and rep["estado"] != review.NO_APLICA:
            gate_val = next((ok for txt, ok in rep["gates"] if txt.startswith("Donaciones")), None)
            if gate_val is not None and gate_val != rec["ok"]:
                issues.append(f"join recon {rec['ok']} != gate cross-sistema del reporte {gate_val}")

    return issues


# --------------------------------------------------------------------------
# Pipeline.
# --------------------------------------------------------------------------

def build_inbox(ong_id, periodo=None, ctx=None):
    """Corre los agentes de etapa sobre el estado compartido y reconcilia. Devuelve
    (ctx, issues). Es lo que reusa la app: arma la bandeja de entregables PENDIENTES
    sin tocar el gate HITL, asi la app firma por etapa con botones."""
    periodo = periodo or schema.PERIODO_DEFAULT
    # "Lectura" de las dos fuentes: pasa por el guarda de solo lectura de la capa de
    # gobierno. Cualquier intento de escritura cortaria aca (READ_ONLY).
    for sistema in schema.mapping_ong(ong_id)["sistemas_conectados"]:
        governance.assert_read_only(sistema, "read")
    d = fc.datos_ong(ong_id)
    ctx = ctx or PotenciarContext(fresh_audit=True, ong_id=ong_id, periodo=periodo)
    ctx.audit("orchestrator", "start",
              f"{d['ong']['nombre']} · periodo {periodo} · nivel de dato {d['tier']} · "
              f"fuentes en solo lectura")

    # Capa de orquestacion (Cowork): junta las dos fuentes que no se hablan
    # (Salesforce y NetSuite) y las CONCILIA. El resultado alimenta el gate
    # cross-sistema del reporte y el cierre (tier A). Ata a ~0 o marca un quiebre.
    rec = fc.reconciliacion_fondeo(d)
    if rec is not None:
        estado = "ok" if rec["ok"] else "QUIEBRE"
        ctx.audit("orchestrator/join", estado,
                  f"Donaciones Salesforce {rec['salesforce']} vs ingreso NetSuite "
                  f"{rec['netsuite']} · diff {rec['diff']} (tolerancia {rec['tol']})")
        ctx.put("orchestrator", {"reconciliacion_fondeo": rec})
        if not rec["ok"]:
            ctx.flag("orchestrator/join", "ALTO",
                     "Las dos fuentes no concilian: el reporte y el cierre nacen bloqueados (fail-closed).")

    # Prerrequisito primero: el diagnostico fija el nivel de dato y que etapas aplican.
    diagnostico_agent.run(d, ctx, periodo)
    # Salidas en el orden del flujo del diagrama: cierre -> forecast -> reporte ->
    # dashboards. Dashboards va al final: lee el runway que dejo el forecast.
    cierre_agent.run(d, ctx, periodo)
    forecast_caja_agent.run(d, ctx, periodo)
    reporte_agent.run(d, ctx, periodo)
    dashboards_agent.run(d, ctx, periodo)

    issues = cross_checks(ctx, d)
    if issues:
        for i in issues:
            ctx.audit("cross_check", "FAIL", i)
        ctx.put("orchestrator", {"status": "halted_inconsistent", "issues": issues})
    else:
        ctx.audit("cross_check", "ok", "los entregables reconcilian con el motor de numeros")
    return ctx, issues


def hitl_gate(ctx):
    """Gate HITL de dos niveles. En modo auto firma cada entregable pendiente
    (registrado 'auto', nunca como firma humana) y, si el reporte queda publicable,
    corre el gate final de publicacion. La firma granular por etapa vive en la app."""
    pend = review.pending(ctx)
    bloq = review.list_deliverables(ctx, estado=review.BLOQUEADO)
    if _auto():
        for dlv in list(pend):
            review.approve(ctx, dlv["id"], note="auto-firmada (POTENCIAR_AUTO_APPROVE)", by="auto")
        if bloq:
            ctx.audit("HITL", "BLOQUEADO",
                      f"{len(bloq)} entregable(s) bloqueado(s) por un control que no cuadra (fail-closed)")
        ok, faltan = review.can_publish(ctx)
        if ok:
            review.publish(ctx, note="gate final auto (CI/replay; NO es una firma humana)", by="auto")
        else:
            ctx.audit("HITL", "sin_publicar", "gate final no habilitado: " + "; ".join(faltan))
        ctx.audit("HITL", "AUTO",
                  f"{len(pend)} entregable(s) auto-firmado(s) (modo CI/replay; NO es una firma humana)")
        return
    print(f"\n  [human-in-the-loop] Hay {len(pend)} entregable(s) pendiente(s) de tu firma.")
    print("  (La firma/edicion/rechazo por etapa y el gate final se hacen en la app Streamlit.)")


def run(ong_id="manos", periodo=None):
    periodo = periodo or schema.PERIODO_DEFAULT
    print("=" * 68)
    print(f"POTENCIAR · operating model de finanzas | ONG {ong_id} · periodo {periodo}")
    print("=" * 68)
    ctx, issues = build_inbox(ong_id, periodo)
    if issues:
        ctx.save()
        print("\n  Pipeline detenido: los entregables no reconcilian con el motor.")
        for i in issues:
            print("   -", i)
        return ctx

    s = review.summary(ctx)
    print(f"\n  Bandeja de entregables: {s['total']} · por estado {s['by_estado']}")
    for dlv in review.ordenados(ctx):
        print(f"   [etapa {dlv['etapa_n']}] {dlv['titulo']:42} · {dlv['estado']}")

    hitl_gate(ctx)
    s2 = review.summary(ctx)
    print(f"\n  Firmados: {s2['firmados']} · pendientes: {s2['pendientes']} · "
          f"bloqueados: {s2['bloqueados']} · publicado: {s2['publicado']}")
    ctx.put("orchestrator", {"status": "done", "resumen": s2})
    saved = ctx.save()
    print(f"  Estado guardado en: {os.path.basename(saved)} ({len(ctx.state['audit'])} eventos de auditoria)")

    # Aditivo: registra la metrica anonima de la corrida (PII-free). Envuelto: nunca
    # rompe el cierre del pipeline.
    try:
        import report_metrics
        report_metrics.record_run(ctx.state)
    except Exception as e:                       # pragma: no cover
        ctx.audit("report_metrics", "skip", f"no se registro la metrica de la corrida: {e}")
    return ctx


if __name__ == "__main__":
    arg_ong = sys.argv[1] if len(sys.argv) > 1 else "manos"
    run(arg_ong)
