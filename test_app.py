"""
test_app.py  -  Pruebas de humo del operating model agentico.

Cubre, de abajo hacia arriba:
  1. el motor deterministico (finance_core) sobre las ONG nombradas + el programa,
  2. los guardas de llm (grounding numerico + PII),
  3. el orquestador de punta a punta en modo replay (auto-firma) sobre cada ONG,
     reconciliando los cross-checks y verificando el fail-closed y el gate final,
  4. la app Streamlit: correr -> firmar etapa -> publicar, sin excepciones.

Corre offline (sin API key). POTENCIAR_AUTO_APPROVE no se usa para la app (ahi se
firma por boton); el orquestador en replay lo usa internamente.
"""

import os
import sys

os.environ["POTENCIAR_USE_LLM"] = "0"
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import finance_core_potenciar as fc
import llm
import review
import schema
import potenciar_orchestrator as orch
from shared_state import PotenciarContext

# ---- 1) motor deterministico ----
for o in fc.ONGS:
    d = fc.datos_ong(o["id"])
    fc.indicadores(d); fc.gates_aplicables(d); fc.escalaciones(d); fc.narrativa_reporte(d)
    if d["tier"] in ("A", "B"):
        fc.ejecucion_fondos(d)
    if d["tier"] == "A":
        fc.forecast_caja_semanal(d); fc.narrativa_caja(d)
        assert fc.runway_meses(d) > 0
res = fc.resumen_programa()
assert res["total"] == 50 and sum(res["por_tier"].values()) == 50
print("ENGINE OK", res["por_tier"], "en_riesgo", res["en_riesgo"])

# ---- 2) guardas de llm ----
ok, off = llm.grounding_ok("Runway de 4.0 meses, saldo minimo 1.234.567.", [4.0, 1234567])
assert ok, off
ok, off = llm.grounding_ok("Runway de 9 meses.", [4.0])           # cifra inventada
assert not ok, "el guarda numerico deberia rechazar 9"
ok, off = llm.pii_ok("El fondeo proviene de varios donantes.", ["Empresa Patrocinante SA"])
assert ok, off
ok, off = llm.pii_ok("Gracias a Empresa Patrocinante SA.", ["Empresa Patrocinante SA"])
assert not ok, "el guarda de PII deberia rechazar el nombre del donante"
# capa de gobierno: la lectura pasa; cualquier escritura corta (solo lectura).
import governance
assert governance.assert_read_only("netsuite", "read") is True
try:
    governance.assert_read_only("netsuite", "write")
    raise AssertionError("una escritura a un sistema de registro deberia cortar")
except governance.ReadOnlyViolation:
    pass
print("GUARDS OK (grounding numerico + PII + solo lectura)")

# ---- 2b) conectores (dos fuentes solo lectura) + join + segregacion PII ----
import json as _json
from connectors import salesforce, netsuite
# cada conector lee por el camino de gobierno (solo lectura)
assert governance.assert_read_only(salesforce.SYSTEM, "read") is True
assert governance.assert_read_only(netsuite.SYSTEM, "read") is True
# join de la orquestacion: un mes limpio ata a 0; un quiebre plantado se marca
clean = fc.datos_ong("manos")
rc = fc.reconciliacion_fondeo(clean)
assert rc is not None and rc["ok"] and rc["diff"] == 0, rc
broken = fc.datos_ong("manos")
broken["ingreso_donaciones_gl"] = broken["donaciones_reconocidas_periodo"] + 10_000_000
rb = fc.reconciliacion_fondeo(broken)
assert rb is not None and not rb["ok"], "el join deberia detectar el quiebre"
# tier C (solo Salesforce): no hay conciliacion cross-sistema (falta NetSuite)
assert fc.reconciliacion_fondeo(fc.datos_ong("luz")) is None
# PII: vive solo en el conector de Salesforce y redact la borra
full = salesforce.donantes_pii("manos")
assert full and all("email" in r and "nombre_contacto" in r for r in full)
red = governance.redact(full)
assert all(not any(k in r for k in ("email", "telefono", "nombre_contacto", "donante")) for r in red)
# la PII (email/telefono/contacto) nunca entra al estado compartido de una corrida
ctx_pii, _ = orch.build_inbox("manos", schema.PERIODO_DEFAULT,
                              PotenciarContext(fresh_audit=True, ong_id="manos", periodo=schema.PERIODO_DEFAULT))
blob = _json.dumps(ctx_pii.state, ensure_ascii=False)
for campo in ("email", "telefono", "nombre_contacto"):
    assert campo not in blob, f"PII filtrada al estado compartido: {campo}"
print("CONNECTORS+JOIN+PII OK", {"recon_diff_limpio": rc["diff"], "quiebre_detectado": not rb["ok"]})

# ---- 3) orquestador end-to-end (replay) ----
os.environ["POTENCIAR_AUTO_APPROVE"] = "1"
vistos = {"publicado": 0, "bloqueado": 0, "no_aplica": 0}
for o in fc.ONGS:
    ctx, issues = orch.build_inbox(o["id"], schema.PERIODO_DEFAULT,
                                   PotenciarContext(fresh_audit=True, ong_id=o["id"], periodo=schema.PERIODO_DEFAULT))
    assert not issues, (o["id"], issues)                          # cross-checks reconcilian
    assert len(ctx.state["inbox"]) == len(schema.ETAPAS)
    # bloqueado <-> algun gate en False (fail-closed coherente)
    for dlv in ctx.state["inbox"]:
        if dlv["estado"] == review.NO_APLICA:
            vistos["no_aplica"] += 1
            assert not schema.etapa_aplica(dlv["clave"], dlv["tier"])
            continue
        falla = any(not g[1] for g in dlv["gates"])
        if dlv["estado"] == review.BLOQUEADO:
            vistos["bloqueado"] += 1
            assert falla
    orch.hitl_gate(ctx)                                           # auto-firma + gate final
    if review.summary(ctx)["publicado"]:
        vistos["publicado"] += 1
    print("  OK", o["id"], o["tier"], review.summary(ctx)["by_estado"])
assert vistos["publicado"] >= 1 and vistos["bloqueado"] >= 1 and vistos["no_aplica"] >= 1, vistos
print("ORCHESTRATOR OK", vistos)

# ---- 4) app Streamlit: correr -> firmar -> publicar ----
os.environ.pop("POTENCIAR_AUTO_APPROVE", None)                    # en la app se firma por boton
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=180).run()
assert not at.exception, at.exception
print("APP INITIAL OK")

# correr una ONG (tier A, set completo)
at.button(key="run").click().run()
assert not at.exception, at.exception
firmar = [b.key for b in at.button if b.key and b.key.startswith("ap_")]
assert firmar, "no hay botones de firma por etapa"
# firmar todas las etapas pendientes (varias pasadas: la lista se reconstruye por rerun)
for _ in range(8):
    pend = [b.key for b in at.button if b.key and b.key.startswith("ap_")]
    if not pend:
        break
    at.button(key=pend[0]).click().run()
    assert not at.exception, at.exception
# todas las etapas quedaron firmadas
inbox = at.session_state["ctx_state"]["inbox"]
firmados = [d for d in inbox if d["estado"] in ("aprobado", "editado", "publicado")]
assert len(firmados) == len(inbox), [(d["clave"], d["estado"]) for d in inbox]
# gate final de publicacion habilitado tras firmar diagnostico+forecast+reporte
assert "publish" in [b.key for b in at.button], "el gate final de publicacion no aparecio"
at.button(key="publish").click().run()
assert not at.exception, at.exception
rep = next(d for d in at.session_state["ctx_state"]["inbox"] if d["clave"] == "reporte")
assert rep["estado"] == "publicado", rep["estado"]
print("APP RUN+SIGN+PUBLISH OK")

# vista programa
at.radio(key="vista").set_value("Programa (consolidado ~50)").run()
assert not at.exception, at.exception
print("APP PROGRAMA OK")

# recorrer todas las ONG en la app (incluye B y C: parciales / no_aplica)
at.radio(key="vista").set_value("Una ONG (en implementacion)").run()
for o in fc.ONGS:
    at.selectbox(key="ong").set_value(o["nombre"]).run()
    at.button(key="run").click().run()
    assert not at.exception, (o["nombre"], at.exception)
    print("  APP OK", o["nombre"], o["tier"])
print("ALL OK")
