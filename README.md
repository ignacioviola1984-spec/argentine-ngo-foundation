# Finance-AI Operating Model · Argentine NGO foundation

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://argentine-ngo-finance-model.streamlit.app)

**Demo en vivo / Live demo:** https://argentine-ngo-finance-model.streamlit.app

> Finance-AI operating model for an Argentine NGO foundation. Public repo uses synthetic data and anonymized institutional references. Real operating model remains private and read-only.

# Status: 
Model built end-to-end, client pre-pilot evaluation phase.

**Operating model** 
Organización y sponsor confirmados, scope acordado, workflow ajustado y código
completo; en curso el mapeo de datos, la validación de fuentes, los permisos de
solo lectura y la definición de controles. Baja el operating model del PDF de
la fundación a un **workflow agéntico**: de los sistemas de registro de la ONG
(Salesforce + NetSuite, solo lectura) a reportes listos para Comisión Directiva y
donantes. La IA asiste al equipo, no lo reemplaza.

Este repositorio es la **implementación de referencia**: corre con datos 100%
sintéticos para ser compartible y reproducible. En la instalación viva, cada conector
apunta a los sistemas reales de la ONG en solo lectura.

Reusa el código determinístico del repo
[ai-finance-engineering](https://github.com/ignacioviola1984-spec/ai-finance-engineering)
y replica sus patrones: **los números los calcula el código; el modelo solo
redacta**, detrás de guardas y de un humano que firma cada etapa.

Corre **sin API key y sin conexión**: offline las narrativas salen de plantillas
determinísticas. Con una key, el modelo redacta y el guarda rechaza cualquier cifra
inventada o nombre de donante (PII).

## Qué muestra

- **Dos fuentes de solo lectura + la capa de orquestación:** Salesforce (fondeo) y
  NetSuite (contable), cada una leída por su conector en `connectors/`, detrás de
  `assert_read_only`. La orquestación junta las dos fuentes (que no se hablan entre
  sí) y **concilia** las donaciones reconocidas en Salesforce contra el ingreso
  posteado en el GL de NetSuite: ata a ~0 o marca un quiebre que deja el reporte y el
  cierre bloqueados (fail-closed). La PII de donantes vive solo en el conector de
  Salesforce y no entra al estado compartido.
- **Una ONG (en implementación):** se corre la capa de orquestación y se recorre cada
  etapa del operating model con su **firma humana**. El diagnóstico es el prerrequisito;
  las cuatro salidas están construidas (código completo), en el orden del diagrama:
  - **Diagnóstico de datos (prerrequisito):** qué sistemas conecta la ONG, qué se
    puede prometer y qué queda fuera de alcance.
  - **Etapa 3 · Cierre mensual:** conciliaciones, devengados, plan vs real.
    **Fail-closed**: si un control no cuadra, el entregable queda bloqueado.
  - **Etapa 4 · Forecast de caja y runway:** proyección semanal cruzando
    timing de donaciones contra pagos.
  - **Etapa 5 · Reporte a CD y donantes:** ejecución por fondo, uso de
    donaciones, estado financiero. Es el artefacto que se publica.
  - **Etapa 6 · Dashboards por audiencia:** CD, donantes, dirección.
- **HITL de dos niveles:** se firma cada etapa (nivel 1) y el reporte pasa por un
  **gate final de publicación** (nivel 2) antes de salir. El operador HITL es Ignacio
  Viola (consultor); la ONG (NGO-side operations owner) controla las conexiones y permisos, y
  los NetSuite implementation/support partners dan soporte a la integración NetSuite.
- **Niveles de dato:** una ONG con ambos sistemas recibe el set completo; con uno
  solo recibe indicadores parciales marcados como tales (honestidad de cobertura).
- **Capa de gobierno (en código):** solo lectura, PII segregada, registro de activos de
  IA versionado, log de sesión append-only.
- **Camino de escala:** mismo patrón más mapeo por ONG (no copiar y pegar). La vista
  **Programa (consolidado ~50)** suma entidades: runway de la cartera, ONG en riesgo,
  cobertura por nivel de dato. Es el resto de las ONG a las que se extiende el modelo.

## Correr local

```bash
pip install -r requirements.txt
streamlit run app.py            # abre en http://localhost:8501
```

Punta a punta desde la terminal (replay, auto-firma):

```bash
python cli.py                   # una ONG (manos)
python cli.py --all             # las ~6 ONG nombradas
```

Para que el modelo redacte (opcional): poné `ANTHROPIC_API_KEY` en `<repo>/.env` y
tildá *Usar Claude para redactar* en la app (o `POTENCIAR_USE_LLM=1` en la CLI).

## Arquitectura (resumen)

| Archivo | Rol |
|---------|-----|
| `connectors/` | los dos sistemas de registro como conectores de solo lectura (Salesforce fondeo + PII segregada, NetSuite contable) |
| `finance_core_potenciar.py` | motor determinístico + backing store seeded + conciliación cross-sistema |
| `schema.py` | etapas del operating model + mapeo por ONG + ancla `AS_OF` |
| `shared_state.py` | `PotenciarContext`: libro común + audit trail append-only |
| `llm.py` | capa de prosa con guarda de grounding numérico + guarda de PII |
| `review.py` | bandeja HITL de dos niveles (firma por etapa + gate de publicación) |
| `agent_base.py` | andamiaje de los agentes + registro de activos de IA |
| `*_agent.py` | los 5 agentes de etapa (diagnóstico, forecast, reporte, cierre, dashboards) |
| `potenciar_orchestrator.py` | capa de orquestación: corre los agentes, cross-checks, gate |
| `governance.py` | la capa de gobierno en código (solo lectura, PII, segregación) |
| `report_metrics.py` | reporte de métricas anónimo (PII-free) |
| `ai_assets/` | prompts versionados, golden output y rúbrica (lo reutilizable) |
| `app.py` | la interfaz Streamlit |

Detalle en [`OPERATING-MODEL.md`](OPERATING-MODEL.md).

## Tests

```bash
python test_app.py
```

Cubre el motor, los guardas (grounding + PII), los **conectores** (solo lectura, el
**join** que ata a ~0 o detecta un quiebre plantado, y la segregación de PII), el
orquestador end-to-end en replay (reconciliación, fail-closed, gate final, cobertura
parcial) y la app (correr → firmar etapa → publicar) sobre las ~6 ONG.

## Deploy

Subí estos archivos a un repo y deployá en Streamlit Community Cloud apuntando a
`app.py`. No requiere secrets ni API key (offline corre con plantillas). Si querés la
redacción con el modelo, cargá `ANTHROPIC_API_KEY` como secret.

## Aclaraciones

Los datos de **este repositorio** son 100% sintéticos y reproducibles (seeded): es la
implementación de referencia, no expone datos de ninguna ONG. En la instalación viva,
los conectores leen los sistemas reales de la ONG en solo lectura. Las donaciones en
USD se consolidan a tipo de cambio de cierre de período (congelado), no a tipo de
cambio vivo. **Solo lectura:** nada escribe en los sistemas de registro. El operating
model está diseñado para una primera ONG; con el cliente, el modelo está en fase
de preparación para su implementación.

---

Preparado por Ignacio Viola · Finance-AI · ex-J.P. Morgan & American Express · 2026
