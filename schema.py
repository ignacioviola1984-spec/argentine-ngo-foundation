"""
schema.py  -  La definicion del operating model y el anclaje de dominio.

Dos cosas:

  1. ETAPAS  - las etapas del operating model del PDF como datos (numero, estado
     PRERREQUISITO/CONSTRUIDA, que nivel de dato requiere cada una, que sistema la alimenta).
     El orquestador y la app recorren esta lista; no hay etapas hardcodeadas en
     dos lugares.

  2. AS_OF y mapping por ONG - AS_OF es el "hoy" de referencia (cierre de periodo),
     asi los numeros sinteticos son reproducibles. `mapping_ong` es el mapeo que
     cada ONG adapta al escalar: que sistemas tiene conectados (nivel de dato),
     su taxonomia de fondos y la convencion de FX. Es el "patron reutilizable mas
     mapeo por ONG, no copiar y pegar" del camino de escala.

Los numeros NO viven aca: los calcula finance_core_potenciar. schema.py solo
define la forma del modelo y el mapeo por entidad.
"""

from datetime import date

import finance_core_potenciar as fc

# "Hoy" de referencia: cierre del periodo 2026-05. Todo lo derivado del dato
# sintetico se ancla aca, igual que un cierre no se reexpresa solo.
AS_OF = date(2026, 5, 31)
PERIODO_DEFAULT = "2026-05"
PERIODOS = ["2026-05", "2026-04", "2026-03"]

# Estado de cada etapa en el operating model en implementacion: el diagnostico es
# el prerrequisito (mapeo y validacion del dato, en curso); las cuatro salidas
# estan construidas (codigo completo), a la espera de salir en vivo con el dato
# validado. El "camino de escala" no es una fase de la etapa: es extender el mismo
# patron al resto de las ONG (mapping_ong por entidad).
PRERREQUISITO, CONSTRUIDA = "PRERREQUISITO", "CONSTRUIDA"

# Niveles de dato (que sistemas de registro estan conectados). Espeja los tiers
# de finance_core: A = ambos, B = solo NetSuite, C = solo Salesforce.
TIER_LABEL = fc.TIER_LABEL


# Las etapas del operating model, como datos. `tier_req` indica que niveles de
# dato habilitan la etapa; una ONG sin esos sistemas recibe el entregable como
# `no_aplica` (honesto sobre su cobertura, nunca un numero inventado).
# Orden del flujo del diagrama: las fuentes (Salesforce + NetSuite) son las tarjetas
# 1 y 2 (la capa de Fuentes); las cuatro salidas son las tarjetas 3 a 6. El
# diagnostico es el prerrequisito (no es una tarjeta del flujo; la conexion ya quedo
# establecida).
ETAPAS = [
    {"n": 0, "clave": "diagnostico", "titulo": "Diagnostico de datos",
     "fase": PRERREQUISITO, "tier_req": ("A", "B", "C"), "agente": "diagnostico_agent",
     "fuente": "Salesforce + NetSuite",
     "desc": "Prerrequisito: calidad y estructura del dato antes de prometer entregables."},
    {"n": 3, "clave": "cierre", "titulo": "Cierre mensual",
     "fase": CONSTRUIDA, "tier_req": ("A", "B"), "agente": "cierre_agent",
     "fuente": "NetSuite",
     "desc": "Conciliaciones, devengados, gasto por fondo, plan vs real (fail-closed)."},
    {"n": 4, "clave": "forecast", "titulo": "Forecast de caja y runway",
     "fase": CONSTRUIDA, "tier_req": ("A", "B"), "agente": "forecast_caja_agent",
     "fuente": "NetSuite (pagos) x Salesforce (timing de donaciones)",
     "desc": "Proyeccion semanal cruzando timing de donaciones contra pagos. Runway a la vista."},
    {"n": 5, "clave": "reporte", "titulo": "Reporte a Comision Directiva y donantes",
     "fase": CONSTRUIDA, "tier_req": ("A", "B", "C"), "agente": "reporte_agent",
     "fuente": "NetSuite + Salesforce",
     "desc": "Ejecucion por proyecto y fondo, uso de donaciones, estado financiero."},
    {"n": 6, "clave": "dashboards", "titulo": "Dashboards por audiencia",
     "fase": CONSTRUIDA, "tier_req": ("A", "B", "C"), "agente": "dashboards_agent",
     "fuente": "NetSuite + Salesforce",
     "desc": "Tableros por audiencia: Comision Directiva, donantes, direccion."},
]

ETAPAS_POR_CLAVE = {e["clave"]: e for e in ETAPAS}
# Etapas que producen un entregable asistido por IA (todas menos las dos fuentes).
ETAPAS_ASISTIDAS = [e for e in ETAPAS if e["clave"] != "diagnostico"]


def etapa_aplica(clave: str, tier: str) -> bool:
    """True si el nivel de dato de la ONG habilita esa etapa."""
    return tier in ETAPAS_POR_CLAVE[clave]["tier_req"]


def mapping_ong(ong_id: str) -> dict:
    """El mapeo que cada ONG adapta al escalar. En la implementacion lo fija el
    diagnostico (prerrequisito) por ONG: que sistemas conecta, su taxonomia de
    fondos y la convencion de tipo de cambio. Es lo que se replica al escalar al
    resto de las ONG."""
    o = fc.get_ong(ong_id)
    tier = o["tier"]
    sistemas = []
    if tier in ("A", "C"):
        sistemas.append("salesforce")
    if tier in ("A", "B"):
        sistemas.append("netsuite")
    return {
        "ong_id": ong_id,
        "ong_nombre": o["nombre"],
        "mision": o["mision"],
        "tier": tier,
        "nivel_dato": TIER_LABEL[tier],
        "sistemas_conectados": sistemas,
        "taxonomia_fondos": "restringido / no restringido",
        "fx_convencion": "tipo de cambio de cierre de periodo (congelado)",
        "fx_cierre": fc.FX_CIERRE,
    }
