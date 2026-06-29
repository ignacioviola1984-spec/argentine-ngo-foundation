# Operating Model · Argentine NGO foundation - arquitectura

Operating model **en implementación para una ONG** (pro-bono). Re-implementa
el mismo **modelo operativo confiable** del repo de finanzas (ai-finance-engineering):
el modelo trabaja, pero hay **controles de código** y un **humano** en los puntos
críticos. No copia código de finanzas; replica los **patrones** y los baja al operating
model del PDF de la fundación. Este repositorio es la implementación de referencia: corre
con datos sintéticos; en vivo, cada conector apunta al sistema real de la ONG en solo lectura.

## El espejo con el repo de finanzas

| Pieza del modelo | Patrón de origen | Qué se reusó |
|--------------------|------------------|--------------|
| `connectors/` (Salesforce, NetSuite) | capa de fuentes de solo lectura | las dos fuentes como camino de lectura real: cada acceso pasa por `assert_read_only`, la PII vive solo en el conector de Salesforce |
| `finance_core_potenciar.py` | `orchestration/finance_core.py` | cálculo determinístico; una sola fuente de números; conciliación cross-sistema |
| `shared_state.py` (`PotenciarContext`) | `cfo-office/shared_state.py` (`CFOContext`) | libro común `put/get`, flags, audit trail, persistencia |
| `review.py` (firma por etapa + gate final) | `cfo-office/review.py` (maker-checker) | HITL de **dos niveles** |
| `llm.py` (guarda de grounding + PII) | `nexo/llm.py` | la prosa pasa por guardas; offline cae a plantilla |
| `potenciar_orchestrator.py` | `cfo_orchestrator.py` | correr agentes sobre el estado, cross-checks, gate |
| `app.py` | `webapp/app.py` | UI con el HITL **como botón**, por etapa |
| `governance.py` + `report_metrics.py` | capa de confiabilidad | solo lectura, PII segregada, métricas anónimas |

## Las etapas (los nodos del PDF, como agentes)

```
   Fuentes (conectores de solo lectura)   Capa de orquestación (Cowork)
   ┌────────────┐ ┌───────────┐      junta las dos fuentes que no se hablan,
   │ Salesforce │ │ NetSuite  │      CONCILIA donaciones (SF) vs ingreso GL (NS)
   │ connectors/│ │connectors/│      -ata a ~0 o marca quiebre-, corre los
   │  (fondeo)  │ │(contable) │      controles y genera las salidas
   └─────┬──────┘ └─────┬─────┘
         │ PII se queda  │           cada lectura pasa por assert_read_only
         └──────┬────────┘
                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  finance_core_potenciar  - los números salen de acá (seeded)  │
   └──────────────────────────────────────────────────────────────┘
                ▼   los agentes solo redactan; el guarda frena cifras inventadas y PII
   ┌──────────────────────────────────────────────────────────────┐
   │  diagnostico_agent  (prerrequisito) - fija el nivel de dato    │
   │  Etapa 3  cierre_agent          (lista) - fail-closed          │
   │  Etapa 4  forecast_caja_agent   (lista) - runway               │
   │  Etapa 5  reporte_agent         (lista) - CD / donantes    ◄─ publicable
   │  Etapa 6  dashboards_agent      (lista) - por audiencia        │
   └──────────────────────────────────────────────────────────────┘
                ▼   cross-checks: los entregables reconcilian con el motor
   ┌──────────────────────────────────────────────────────────────┐
   │  HITL nivel 1: firma por etapa (aprobar / editar / rechazar)  │
   │  HITL nivel 2: gate final de publicación del reporte          │
   └──────────────────────────────────────────────────────────────┘
                ▼   solo lo firmado/publicado sale
   audit_log.jsonl (log de sesión, append-only)  +  potenciar_state.json
```

Cada etapa produce **un entregable** por ONG por período. El `tier` de la ONG (qué
sistemas conecta) decide qué etapas aplican: una ONG sin NetSuite recibe el forecast
y el cierre como `no_aplica` (cobertura parcial, honesta), nunca un número inventado.

## Las dos capas de confiabilidad

1. **Controles de código entre el modelo y la salida.**
   - **Guarda de grounding** (`llm.py`): rechaza cualquier cifra del modelo que no
     esté en el payload del entregable; cae a la plantilla determinística.
   - **Guarda de PII** (`llm.py`): rechaza cualquier narrativa que mencione un
     nombre de donante. La PII se queda en Salesforce.
   - **Join cross-sistema** (`finance_core.reconciliacion_fondeo`, corrido por la
     orquestación): las donaciones reconocidas en Salesforce concilian contra el
     ingreso posteado en el GL de NetSuite. Las dos cifras vienen de conectores
     distintos; el join las compara (no las asume iguales): ata a ~0 o marca un
     quiebre que deja el reporte y el cierre bloqueados. Queda en el log de sesión.
   - **Cross-checks** (`potenciar_orchestrator.cross_checks`): el inbox reconcilia
     con el motor - una etapa = un entregable, `bloqueado ⇔ un gate falla`, el
     runway del forecast == el de dashboards, el ejecutado del cierre == la suma de
     fondos. Si un agente deriva distinto, salta acá y no en la salida.
   - **Fail-closed**: si un control determinístico no cuadra, el entregable nace
     `bloqueado` y no se firma ni se publica hasta corregir el dato.

2. **Humano en el punto crítico (HITL de dos niveles).**
   - Nivel 1: el consultor firma (aprueba / edita / rechaza) **cada etapa**.
   - Nivel 2: el reporte -el artefacto externo- solo se **publica** con el
     diagnóstico y el forecast firmados y el reporte aprobado. Es la firma final.
   - Todo queda con **quién / qué / cuándo** (revisor, nota, timestamps).

## La capa de gobierno (del PDF, hecha código) - `governance.py`

- **Solo lectura**: `READ_ONLY = True`; `assert_read_only` corta cualquier escritura
  a un sistema de registro. Ningún módulo tiene ruta de escritura.
- **Datos de donantes**: la PII nunca sale de Salesforce; `redact()` y el control de
  privacidad de `report_metrics` lo hacen cumplir. Segregación por ONG (`ong_id`).
- **Registro de activos de IA**: prompts versionados + golden output + rúbrica en
  `ai_assets/`. Es lo reutilizable al escalar a otra ONG.
- **Log de sesión**: traza append-only en `audit_log.jsonl`.

## Separación determinístico / LLM (la regla dura)

- **Determinístico (código):** números, fechas, montos, ejecución, runway, gates,
  severidad, selección de etapa, cross-checks, métricas.
- **LLM (prosa):** la narrativa de cada entregable - y siempre pasando por los
  guardas. Offline, plantillas determinísticas. Lo que **nunca** cambia: ningún
  número proviene del modelo.

## Replay

Con `POTENCIAR_AUTO_APPROVE=1` el orquestador corre de punta a punta sin
intervención (CI/replay), firmando como `auto` (nunca como firma humana) y
reproduciendo los mismos números. `python cli.py --all` corre las ~6 ONG nombradas.
