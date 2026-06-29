"""
app.py  -  Operating Model de Finanzas con IA · Argentine NGO foundation (Streamlit).

La cara del operating model agentico: se elige una ONG, se corre la capa de
orquestacion (que conecta las dos fuentes, cruza los datos y corre los agentes de
etapa sobre un estado compartido) y se recorre cada etapa con su firma humana.

  - Los NUMEROS los calcula el codigo (finance_core_potenciar). El modelo solo
    redacta la narrativa, y un guarda rechaza cualquier cifra inventada o PII.
  - HITL de dos niveles: firma por etapa + gate final de publicacion del reporte.
  - Capa de gobierno en codigo: solo lectura, PII segregada, registro de activos de
    IA versionado, log de sesion append-only.

Corre sin API key y sin conexion: offline las narrativas salen de plantillas
deterministicas. Datos 100% sinteticos; no representan a ninguna ONG real.

Correr:  pip install -r requirements.txt  &&  streamlit run app.py
"""

import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
    import paths
    load_dotenv(paths.ENV_PATH)
except Exception:
    pass

# En un host, la key llega como secret -> al entorno. Envuelto: sin secrets, acceder
# a st.secrets puede lanzar y no queremos que rompa el arranque local.
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

import finance_core_potenciar as fc
import governance
import llm
import potenciar_orchestrator as orch
import report_metrics
import review
import schema
from shared_state import PotenciarContext

AZUL = "#16365C"
AZUL2 = "#1F6FB2"
SECUENCIA = ["#1F6FB2", "#16365C", "#5B9BD5", "#9DC3E6", "#2E8B57", "#C0504D"]
FASE_COLOR = {"PRERREQUISITO": "🟡 Prerrequisito", "CONSTRUIDA": "🔵 Construida"}

st.set_page_config(page_title="Operating Model · Argentine NGO foundation", layout="wide")


def money(x):
    return f"$ {x:,.0f}".replace(",", ".")


# ==========================================================================
# Estado / contexto
# ==========================================================================
def _ctx():
    """Reconstruye un PotenciarContext atado al estado de sesion (asi las firmas
    persisten entre reruns)."""
    if not st.session_state.get("ctx_state"):
        return None
    ctx = PotenciarContext()
    ctx.state = st.session_state.ctx_state
    return ctx


def _persist(ctx):
    st.session_state.ctx_state = ctx.state


# ==========================================================================
# Encabezado
# ==========================================================================
st.title("Operating Model de Finanzas con IA · Argentine NGO foundation")
st.caption(
    "En implementacion para una ONG (pro-bono): organizacion y sponsor confirmados, "
    "scope acordado, workflow ajustado y codigo completo; en curso el mapeo de datos, "
    "la validacion de fuentes, los permisos de solo lectura y los controles. De los "
    "sistemas de registro (Salesforce + NetSuite, solo lectura) a reportes listos "
    "para Comision Directiva y donantes. La IA asiste al equipo, no lo reemplaza. "
    "Los numeros los calcula el codigo; el modelo solo redacta. Operado por un "
    "consultor como human-in-the-loop."
)
st.caption(
    "Esta interfaz es la implementacion de referencia: corre con datos 100% "
    "sinteticos para ser compartible y reproducible. En la instalacion viva, cada "
    "conector apunta a los sistemas reales de la ONG en solo lectura."
)

# ==========================================================================
# Barra lateral: fuente + correr
# ==========================================================================
with st.sidebar:
    st.header("1) Vista")
    vista = st.radio("Vista", ["Una ONG (en implementacion)", "Programa (consolidado ~50)"], key="vista")

    ong_id, periodo = None, schema.PERIODO_DEFAULT
    if vista.startswith("Una ONG"):
        opciones = {o["nombre"]: o["id"] for o in fc.ONGS}
        nombre_sel = st.selectbox("ONG", list(opciones.keys()), key="ong")
        ong_id = opciones[nombre_sel]
        periodo = st.selectbox("Periodo", schema.PERIODOS, key="periodo")

        st.header("2) Redaccion")
        usar_llm = st.checkbox("Usar Claude para redactar (requiere API key)", value=llm.use_llm())
        st.caption("Sin tildar, las narrativas salen de plantillas deterministicas "
                   "(gratis, reproducible). Con Claude, el modelo redacta y el guarda "
                   "rechaza cualquier cifra inventada o nombre de donante (PII).")

        st.header("3) Correr")
        if st.button("▶ Correr el operating model", type="primary", width="stretch", key="run"):
            os.environ["POTENCIAR_USE_LLM"] = "1" if usar_llm else "0"
            try:
                ctx = PotenciarContext(fresh_audit=True, ong_id=ong_id, periodo=periodo)
                ctx, issues = orch.build_inbox(ong_id, periodo, ctx)
                st.session_state.ctx_state = ctx.state
                st.session_state.built_for = (ong_id, periodo)
                st.session_state.issues = issues
                st.session_state.metrics_md = None
            except Exception as e:
                st.session_state.ctx_state = None
                st.error(f"No se pudo correr el operating model: {e}")
        st.caption(f"Modo de redaccion: {'Claude (LLM)' if llm.use_llm() else 'plantillas'}")


# ==========================================================================
# Guia
# ==========================================================================
with st.expander("Como leer esta interfaz"):
    st.write(
        "Cada etapa del operating model se corre y se firma con un gate humano. El "
        "diagnostico de datos (prerrequisito) fija que se puede prometer. El reporte a CD y "
        "donantes ademas pasa por un gate final de publicacion (segundo nivel de HITL). "
        "Una ONG con un solo sistema recibe indicadores parciales, marcados como tales: "
        "honestidad de cobertura, nunca un numero inventado para tapar el sistema que falta."
    )


# ==========================================================================
# VISTA PROGRAMA
# ==========================================================================
def vista_programa():
    st.subheader("Indicadores a nivel programa · cartera de ~50 ONG")
    st.write(
        "Misma logica, sumando entidades. El identificador de entidad pasa de una ONG "
        "a la cartera. Es la bajada del proyecto de indicadores: salud de la red "
        "instrumentada. Patron reutilizable mas mapeo por ONG, no copiar y pegar."
    )
    res = fc.resumen_programa()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ONG instrumentadas", res["total"])
    c2.metric("ONG en riesgo", res["en_riesgo"], help="Runway por debajo de 3 meses")
    c3.metric("Con ambos sistemas (set completo)", res["por_tier"]["A"])
    c4.metric("Cobertura set completo", f"{res['por_tier']['A']/res['total']*100:.0f}%")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Distribucion de runway en la cartera**")
        dfb = pd.DataFrame({"rango": list(res["buckets"].keys()),
                            "ONG": list(res["buckets"].values())})
        fig = px.bar(dfb, x="rango", y="ONG", color="rango",
                     color_discrete_sequence=["#C0504D", "#E8A33D", "#2E8B57"])
        fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
    with col_b:
        st.markdown("**Cobertura por nivel de dato**")
        dft = pd.DataFrame({
            "tier": ["Ambos sistemas", "Solo contable", "Solo fondeo"],
            "ONG": [res["por_tier"]["A"], res["por_tier"]["B"], res["por_tier"]["C"]],
        })
        fig2 = px.bar(dft, x="ONG", y="tier", orientation="h", color="tier",
                      color_discrete_sequence=SECUENCIA)
        fig2.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig2, width="stretch")

    st.markdown("**Cartera (muestra)**")
    df = pd.DataFrame(res["universo"])
    df["runway"] = df["runway"].apply(lambda v: f"{v:.1f}" if v is not None else "s/d")
    df["ejecucion"] = df["ejecucion"].apply(lambda v: f"{v*100:.0f}%" if v is not None else "s/d")
    df["estado"] = [("EN RIESGO" if (r != "s/d" and float(r) < 3) else "ok") for r in df["runway"]]
    st.dataframe(
        df.rename(columns={"ong": "ONG", "tier": "Nivel", "runway": "Runway (meses)",
                           "ejecucion": "Ejecucion", "completitud": "Completitud", "estado": "Estado"}),
        hide_index=True, width="stretch", height=300,
    )
    st.caption("La vista de programa es honesta sobre su cobertura: las ONG con un solo "
               "sistema reciben indicadores parciales.")


# ==========================================================================
# Render de una etapa (numeros + graficos + gates + narrativa + firma)
# ==========================================================================
def _graficos_etapa(clave, d, tier):
    """Los graficos deterministicos de cada etapa (los numeros salen del motor)."""
    has_contable = tier in ("A", "B")
    has_fondeo = tier in ("A", "C")

    if clave == "forecast" and tier == "A":
        rw = fc.runway_meses(d)
        m1, m2 = st.columns([1, 3])
        m1.metric("Runway", f"{rw:.1f} meses")
        dff = pd.DataFrame(fc.forecast_caja_semanal(d))
        fig = px.line(dff, x="semana", y="saldo_proyectado", markers=True,
                      color_discrete_sequence=[AZUL2])
        fig.update_layout(height=260, margin=dict(t=10, b=10), yaxis_title="Saldo proyectado (ARS)")
        m2.plotly_chart(fig, width="stretch", key=f"g_fc_{d['ong']['id']}")

    elif clave == "reporte":
        cols = st.columns(2)
        if has_contable:
            with cols[0]:
                st.markdown("**Ejecucion por fondo (plan vs real)**")
                dfe = pd.DataFrame(fc.ejecucion_fondos(d))
                dfm = dfe.melt(id_vars=["fondo"], value_vars=["presupuesto", "ejecutado"],
                               var_name="tipo", value_name="ARS")
                fig = px.bar(dfm, x="fondo", y="ARS", color="tipo", barmode="group",
                             color_discrete_sequence=[AZUL2, AZUL])
                fig.update_layout(height=260, margin=dict(t=10, b=10), xaxis_title="", legend_title="")
                st.plotly_chart(fig, width="stretch", key=f"g_rep_ej_{d['ong']['id']}")
            with cols[1]:
                st.markdown("**Composicion del gasto (programa vs administracion)**")
                dfcd = pd.DataFrame({"destino": ["Programa", "Administracion"],
                                     "ARS": [d["gasto_programa"], d["gasto_admin"]]})
                figcd = px.pie(dfcd, names="destino", values="ARS", hole=0.55,
                               color_discrete_sequence=[AZUL2, "#9DC3E6"])
                figcd.update_layout(height=260, margin=dict(t=10, b=10), legend_title="")
                st.plotly_chart(figcd, width="stretch", key=f"g_rep_pa_{d['ong']['id']}")
        if has_fondeo:
            st.markdown("**Fondeo por donante** (la PII se queda en Salesforce; aca solo el monto)")
            dfd = pd.DataFrame(d["donantes"]).sort_values("monto_ars", ascending=False)
            figd = px.bar(dfd, x="donante", y="monto_ars", color_discrete_sequence=[AZUL2])
            figd.update_layout(height=240, margin=dict(t=10, b=10), xaxis_title="", yaxis_title="Monto (ARS)")
            st.plotly_chart(figd, width="stretch", key=f"g_rep_don_{d['ong']['id']}")

    elif clave == "cierre" and has_contable:
        ejc = fc.ejecucion_fondos(d)
        tot_pres = sum(f["presupuesto"] for f in ejc)
        tot_ejec = sum(f["ejecutado"] for f in ejc)
        filas = [{"Fondo": f["fondo"], "Tipo": f["tipo"], "Presupuesto": money(f["presupuesto"]),
                  "Ejecutado": money(f["ejecutado"]), "Desvio": money(f["ejecutado"] - f["presupuesto"]),
                  "Ejecucion": f"{f['ejecucion_pct']*100:.0f}%"} for f in ejc]
        filas.append({"Fondo": "TOTAL", "Tipo": "", "Presupuesto": money(tot_pres),
                      "Ejecutado": money(tot_ejec), "Desvio": money(tot_ejec - tot_pres),
                      "Ejecucion": f"{(tot_ejec/tot_pres*100) if tot_pres else 0:.0f}%"})
        st.markdown("**Plan vs real por fondo**")
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        ap = d["ap"]
        cm = st.columns(3)
        cm[0].metric("Gasto del periodo", money(tot_ejec))
        cm[1].metric("Devengado pendiente (AP)", money(sum(ap.values())))
        cm[2].metric("Devengado vencido (+60d)", money(ap["mas_60"]))

    elif clave == "dashboards":
        t_cd, t_don, t_dir = st.tabs(["Comision Directiva", "Donantes", "Direccion"])
        with t_cd:
            if has_contable:
                st.markdown("**Composicion del gasto**")
                dfcd = pd.DataFrame({"destino": ["Programa", "Administracion"],
                                     "ARS": [d["gasto_programa"], d["gasto_admin"]]})
                figcd = px.pie(dfcd, names="destino", values="ARS", hole=0.55,
                               color_discrete_sequence=[AZUL2, "#9DC3E6"])
                figcd.update_layout(height=240, margin=dict(t=10, b=10), legend_title="")
                st.plotly_chart(figcd, width="stretch", key=f"g_db_cd_{d['ong']['id']}")
            else:
                st.caption("Sin dato contable: el tablero de CD muestra solo fondeo.")
        with t_don:
            if has_fondeo:
                st.metric("Concentracion top-3", f"{fc.concentracion_donantes(d)*100:.0f}%")
                dfd = pd.DataFrame(d["donantes"]).sort_values("monto_ars", ascending=False)
                figd = px.bar(dfd, x="donante", y="monto_ars", color_discrete_sequence=[AZUL2])
                figd.update_layout(height=240, margin=dict(t=10, b=10), xaxis_title="", yaxis_title="Monto (ARS)")
                st.plotly_chart(figd, width="stretch", key=f"g_db_don_{d['ong']['id']}")
            else:
                st.caption("Sin Salesforce: no hay tablero de donantes.")
        with t_dir:
            if has_contable:
                ap = d["ap"]
                st.markdown("**Aging de cuentas por pagar (AP)**")
                dfa = pd.DataFrame({"bucket": ["Corriente", "1-30", "31-60", "+60"],
                                    "ARS": [ap["corriente"], ap["1_30"], ap["31_60"], ap["mas_60"]]})
                fig = px.bar(dfa, x="bucket", y="ARS", color_discrete_sequence=[AZUL2])
                fig.update_layout(height=240, margin=dict(t=10, b=10), xaxis_title="")
                st.plotly_chart(fig, width="stretch", key=f"g_db_ap_{d['ong']['id']}")
            else:
                st.caption("Sin dato contable: no hay tablero operativo.")


def render_etapa(ctx, dlv, d):
    fase = FASE_COLOR.get(dlv["fase"], dlv["fase"])
    estado = dlv["estado"]
    icono = {"pendiente": "🔵", "aprobado": "✅", "editado": "✅", "publicado": "📣",
             "rechazado": "✖", "bloqueado": "⛔", "no_aplica": "➖"}.get(estado, "·")
    st.markdown(f"#### {icono} Etapa {dlv['etapa_n']} · {dlv['titulo']}  -  {fase}")
    st.caption(schema.ETAPAS_POR_CLAVE[dlv["clave"]]["desc"] + f"  ·  Fuente: {schema.ETAPAS_POR_CLAVE[dlv['clave']]['fuente']}")

    if estado == review.NO_APLICA:
        st.info(f"➖ No aplica · {dlv['detalle']}")
        return

    # Graficos deterministicos de la etapa.
    _graficos_etapa(dlv["clave"], d, dlv["tier"])

    st.markdown(f"**Resumen determinístico:** {dlv['detalle']}")

    # Gates deterministicos.
    if dlv["gates"]:
        st.markdown("**Controles deterministicos (gates)**")
        for texto, ok in dlv["gates"]:
            st.markdown(("✅ " if ok else "⛔ ") + texto)

    if estado == review.BLOQUEADO:
        st.error("Entregable BLOQUEADO (fail-closed): un control no cuadra. No se firma ni "
                 "se publica un numero sobre un control que falla, hasta corregir el dato.")
        return

    # Narrativa + firma por etapa (nivel 1 del HITL).
    src = dlv["datos"].get("_narrativa_source", "template")
    src_label = {"llm": "redactada por el modelo (guarda OK)",
                 "template": "plantilla deterministica",
                 "template_guarded": "plantilla (el modelo se rechazo por el guarda)",
                 "template_error": "plantilla (sin conexion al modelo)"}.get(src, src)
    ver = dlv["datos"].get("_prompt_version", "?")

    if estado in (review.APROBADO, review.EDITADO, review.PUBLICADO):
        st.success(f"Firmado por {dlv['decided_by']}" + (f" · nota: {dlv['decision_note']}" if dlv["decision_note"] else ""))
        st.markdown("> " + (dlv["narrativa_final"] or dlv["narrativa_propuesta"]))
        st.caption(f"Narrativa: {src_label} · prompt v{ver}")
    elif estado == review.RECHAZADO:
        st.warning(f"Rechazado por {dlv['decided_by']}" + (f" · {dlv['decision_note']}" if dlv["decision_note"] else ""))
    else:  # pendiente
        nueva = st.text_area("Narrativa propuesta (editable)", dlv["narrativa_propuesta"],
                             key=f"msg_{dlv['id']}", height=110)
        st.caption(f"Narrativa: {src_label} · prompt v{ver}")
        nota = st.text_input("Nota de firma (opcional)", key=f"nota_{dlv['id']}")
        b1, b2, b3 = st.columns(3)
        if b1.button("✓ Firmar", key=f"ap_{dlv['id']}", width="stretch"):
            review.approve(ctx, dlv["id"], note=nota); _persist(ctx); st.rerun()
        if b2.button("✎ Firmar con edicion", key=f"ed_{dlv['id']}", width="stretch"):
            review.edit(ctx, dlv["id"], nueva, note=nota); _persist(ctx); st.rerun()
        if b3.button("✗ Rechazar", key=f"re_{dlv['id']}", width="stretch"):
            review.reject(ctx, dlv["id"], note=nota); _persist(ctx); st.rerun()


# ==========================================================================
# Gate final de publicacion (nivel 2)
# ==========================================================================
def render_gate_publicacion(ctx):
    st.divider()
    st.markdown("### 🔒 Gate final de publicacion (segundo nivel de HITL)")
    st.caption("El reporte a Comision Directiva y donantes -el artefacto que sale hacia "
               "afuera- solo se publica con el prerrequisito (diagnostico) y el forecast "
               "firmados, y el reporte aprobado. Es la firma final del consultor.")
    rep = review.get(ctx, "reporte")
    if rep and rep["estado"] == review.PUBLICADO:
        st.success("📣 Reporte PUBLICADO a Comision Directiva y donantes.")
        st.markdown("> " + (rep["narrativa_final"] or rep["narrativa_propuesta"]))
        return
    ok, faltan = review.can_publish(ctx)
    if ok:
        nota = st.text_input("Nota de publicacion (opcional)", key="nota_publish")
        if st.button("📣 Publicar a Comision Directiva y donantes", type="primary", key="publish"):
            review.publish(ctx, note=nota); _persist(ctx); st.rerun()
    else:
        st.info("Gate final no habilitado todavia. Falta: " + "; ".join(faltan))


# ==========================================================================
# Capa de gobierno y trazabilidad
# ==========================================================================
def render_gobierno(ctx, d):
    st.divider()
    st.markdown("### Capa de gobierno y trazabilidad")
    g = st.columns(4)
    g[0].markdown("**Solo lectura**")
    g[0].caption(f"Los conectores (connectors/) leen NetSuite y Salesforce con scope "
                 f"minimo; cada lectura pasa por assert_read_only. La IA no escribe "
                 f"(READ_ONLY={governance.READ_ONLY}).")
    g[1].markdown("**Datos de donantes (PII)**")
    g[1].caption("La PII nunca sale de Salesforce. Segregacion por ONG. El reporte de "
                 "metricas se genera anonimo (control de privacidad).")
    g[2].markdown("**Registro de activos de IA**")
    versiones = {dlv["clave"]: dlv["datos"].get("_prompt_version", "?")
                 for dlv in ctx.state["inbox"] if dlv["estado"] != review.NO_APLICA}
    g[2].caption("Prompts versionados, golden outputs y rubrica (ai_assets/). "
                 f"Versiones en uso: {', '.join(sorted(set(versiones.values())))}.")
    g[3].markdown("**Log de sesion**")
    g[3].caption(f"Traza append-only: {len(ctx.state['audit'])} eventos en esta corrida "
                 "(fecha, agente, accion, revisor).")

    st.markdown("**Reporte de metricas (anonimo, PII-free)**")
    cm1, cm2 = st.columns([1, 2])
    if cm1.button("📊 Generar reporte de metricas (anonimizado)", width="stretch"):
        try:
            st.session_state.metrics_md = report_metrics.generate(ctx.state)["md"]
            st.success("Reporte generado. No contiene datos de donantes, solo conteos y porcentajes.")
        except report_metrics.PrivacyError as e:
            st.session_state.metrics_md = None
            st.error(f"No se genero (control de privacidad): {e}")
    if st.session_state.get("metrics_md"):
        cm2.download_button("⬇ Descargar metrics_report.md", st.session_state.metrics_md,
                            file_name="metrics_report.md", mime="text/markdown",
                            width="stretch")


def render_audit(ctx):
    st.divider()
    st.markdown("### Trazabilidad (audit trail)")
    aud = ctx.state.get("audit", [])
    if aud:
        df = pd.DataFrame(aud)
        df = df.rename(columns={"ts": "hora", "agent": "agente", "status": "accion",
                                "detail": "detalle", "revisor": "revisor"})
        st.dataframe(df[["hora", "agente", "accion", "revisor", "detalle"]],
                     hide_index=True, width="stretch", height=260)
    else:
        st.caption("Vacia. Corré el operating model para empezar a registrar.")


# ==========================================================================
# Fuentes (dos sistemas de registro) + capa de orquestacion (el join)
# ==========================================================================
def render_fuentes(d, mp):
    st.markdown("### Fuentes y capa de orquestacion")
    st.caption("Dos sistemas de registro en solo lectura. La capa de orquestacion los "
               "junta (no se hablan entre si) y concilia lo que cada uno reporta.")
    con = mp["sistemas_conectados"]
    cols = st.columns(2)
    with cols[0]:
        if "salesforce" in con:
            st.markdown("**🟢 Salesforce · fondeo · solo lectura**")
            st.caption(governance.SISTEMAS["salesforce"]["scope"])
            sc = st.columns(3)
            sc[0].metric("Donantes", len(d.get("donantes", [])))
            sc[1].metric("Campañas", d.get("campanias", "s/d"))
            sc[2].metric("Voluntarios", d.get("voluntarios", "s/d"))
            st.caption("La PII (email, teléfono, contacto) se queda en Salesforce: no entra al estado compartido.")
        else:
            st.markdown("**⚪ Salesforce · no conectado**")
            st.caption("Sin Salesforce: no hay datos de fondeo para esta ONG.")
    with cols[1]:
        if "netsuite" in con:
            st.markdown("**🟢 NetSuite · contable · solo lectura**")
            st.caption(governance.SISTEMAS["netsuite"]["scope"])
            nc = st.columns(2)
            nc[0].metric("Caja (NetSuite)", money(d["caja"]))
            nc[1].metric("Ingreso donaciones (GL)", money(d["ingreso_donaciones_gl"]))
        else:
            st.markdown("**⚪ NetSuite · no conectado**")
            st.caption("Sin NetSuite: no hay datos contables para esta ONG.")

    rec = fc.reconciliacion_fondeo(d)
    if rec is None:
        st.info("🔗 Conciliación cross-sistema: no aplica (requiere los dos sistemas conectados).")
    elif rec["ok"]:
        st.success(f"🔗 Join Salesforce ↔ NetSuite: concilia. Donaciones {money(rec['salesforce'])} "
                   f"= ingreso en el GL {money(rec['netsuite'])} · diferencia {money(rec['diff'])} "
                   f"(tolerancia {money(rec['tol'])}).")
    else:
        st.error(f"🔗 Join Salesforce ↔ NetSuite: QUIEBRE. Donaciones {money(rec['salesforce'])} "
                 f"vs ingreso en el GL {money(rec['netsuite'])} · diferencia {money(rec['diff'])}. "
                 "El reporte y el cierre nacen bloqueados (fail-closed).")

    st.caption(
        f"**Accesos y soporte (gobernado por la ONG):** {governance.ROLES['operador_hitl']} · "
        f"{governance.ROLES['gatekeeper']} · {governance.ROLES['soporte_netsuite']}."
    )


# ==========================================================================
# VISTA UNA ONG
# ==========================================================================
def vista_ong():
    ctx = _ctx()
    built_for = st.session_state.get("built_for")
    if ctx is None or built_for != (ong_id, periodo):
        st.info("Elegí la ONG y el periodo, y tocá **Correr el operating model** en la barra lateral.")
        return
    if st.session_state.get("issues"):
        st.error("Los entregables no reconcilian con el motor de numeros; revisá los datos:")
        for i in st.session_state["issues"]:
            st.write("-", i)
        return

    d = fc.datos_ong(ong_id)
    o = d["ong"]
    mp = schema.mapping_ong(ong_id)
    st.subheader(o["nombre"])
    st.write(f"Mision: {o['mision']}  ·  Nivel de dato: **{mp['nivel_dato']}**  ·  Periodo: {periodo}")
    badges = []
    if "salesforce" in mp["sistemas_conectados"]:
        badges.append("🟢 Salesforce · fondeo · solo lectura")
    if "netsuite" in mp["sistemas_conectados"]:
        badges.append("🟢 NetSuite · contable · solo lectura")
    st.caption("  ·  ".join(badges))

    st.divider()
    render_fuentes(d, mp)
    st.divider()

    s = review.summary(ctx)
    k = st.columns(4)
    k[0].metric("Entregables", s["total"])
    k[1].metric("Firmados", s["firmados"])
    k[2].metric("Bloqueados", s["bloqueados"], help="Fail-closed: un control no cuadra")
    k[3].metric("Pendientes", s["pendientes"])

    # Etapas en el orden del operating model.
    for dlv in review.ordenados(ctx):
        st.divider()
        render_etapa(ctx, dlv, d)

    render_gate_publicacion(ctx)
    render_gobierno(ctx, d)
    render_audit(ctx)


# ==========================================================================
# Router
# ==========================================================================
if vista.startswith("Programa"):
    vista_programa()
else:
    vista_ong()

st.divider()
st.caption("Preparado por Ignacio Viola · Finance-AI · ex-J.P. Morgan & American Express · "
           "operating model en implementacion para una ONG · corre con datos sinteticos de referencia · 2026")
