"""
finance_core_potenciar.py  -  Motor deterministico del operating model.

Principio (igual que el repo original): TODO numero se computa aca, en codigo.
El modelo nunca inventa una cifra; en la version viva, el modelo redacta la
narrativa sobre estos numeros y los conectores reemplazan a los datos sinteticos.

Datos 100% sinteticos y reproducibles (seeded). No representan a ninguna ONG real.
Moneda base: ARS. Las donaciones en USD se consolidan a tipo de cambio de cierre
de periodo (congelado), no a tipo de cambio vivo: un periodo cerrado no se
reexpresa solo.
"""

import random
from datetime import date, timedelta

# Tipo de cambio de cierre de periodo (congelado). Mismo criterio que el repo: FX de cierre, no vivo.
FX_CIERRE = {"USD": 1180.0, "EUR": 1270.0, "ARS": 1.0}

# Las ~50 ONG del stack integrado son el universo direccionable. Aca mostramos
# una muestra nombrada para la vista por ONG, y generamos ~50 para la vista programa.
ONGS = [
    {"id": "manos",   "nombre": "ONG Demo A",   "tier": "A", "mision": "Primera infancia"},
    {"id": "raices",  "nombre": "ONG Demo B",       "tier": "A", "mision": "Educacion rural"},
    {"id": "camino",  "nombre": "ONG Demo C",       "tier": "A", "mision": "Inclusion laboral"},
    {"id": "sembrar", "nombre": "ONG Demo D",                "tier": "B", "mision": "Seguridad alimentaria"},
    {"id": "abrigo",  "nombre": "ONG Demo E",                 "tier": "B", "mision": "Personas en situacion de calle"},
    {"id": "luz",     "nombre": "ONG Demo F",        "tier": "C", "mision": "Salud comunitaria"},
]

TIER_LABEL = {
    "A": "Ambos sistemas (NetSuite + Salesforce)",
    "B": "Solo NetSuite (contable)",
    "C": "Solo Salesforce (fondeo)",
}

# Umbrales de escalamiento (deterministicos, en codigo).
RUNWAY_CRITICO = 3.0     # meses
RUNWAY_ALERTA = 6.0
CONCENTRACION_ALERTA = 0.55   # % del fondeo en pocos donantes
EJECUCION_SOBRE = 1.00        # ejecucion por encima del presupuesto del fondo


def _rng(ong_id):
    return random.Random("potenciar-" + ong_id)


def _money(x):
    return f"$ {x:,.0f}".replace(",", ".")


def get_ong(ong_id):
    for o in ONGS:
        if o["id"] == ong_id:
            return o
    return None


# --------------------------------------------------------------------------
# Backing store sintetico (el stand-in de las bases productivas de los dos
# sistemas). Los conectores de solo lectura (connectors/) leen de aca; en vivo,
# cada conector apunta a su sistema real. datos_ong() compone las dos lecturas.
# --------------------------------------------------------------------------
def _backing_store(ong_id):
    o = get_ong(ong_id)
    r = _rng(ong_id)
    tier = o["tier"]

    # --- Lado contable (NetSuite): caja, gasto, fondos, AP ---
    caja = r.randint(4, 28) * 1_000_000
    gasto_programa = r.randint(35, 70) * 100_000
    gasto_admin = r.randint(8, 22) * 100_000
    gasto_mensual = gasto_programa + gasto_admin

    fondos = []
    nombres_fondo = [
        ("Programa Becas", "restringido"),
        ("Operacion general", "no restringido"),
        ("Proyecto Merienda", "restringido"),
        ("Infraestructura", "restringido"),
    ]
    for nf, tipo in nombres_fondo:
        presupuesto = r.randint(20, 90) * 100_000
        # ejecucion entre 30% y 110%; una ONG puede sobre-ejecutar (gate lo marca)
        ejec_pct = r.uniform(0.30, 1.08)
        ejecutado = round(presupuesto * ejec_pct)
        fondos.append({
            "fondo": nf, "tipo": tipo,
            "presupuesto": presupuesto, "ejecutado": ejecutado,
        })

    # Cuentas por pagar (AP) con aging
    ap = {
        "corriente": r.randint(3, 12) * 100_000,
        "1_30": r.randint(1, 8) * 100_000,
        "31_60": r.randint(0, 4) * 100_000,
        "mas_60": r.randint(0, 3) * 100_000,
    }

    # --- Lado fondeo (Salesforce): donantes, donaciones, AR ---
    donantes = []
    base = ["Empresa Patrocinante SA", "Fundacion Internacional", "Donante particular A",
            "Campania Fin de Anio", "Subsidio Municipal", "Donante particular B"]
    for nombre in base:
        monto = r.randint(4, 40) * 100_000
        moneda = "USD" if "Internacional" in nombre and tier != "B" else "ARS"
        donantes.append({"donante": nombre, "monto_ars": monto if moneda == "ARS" else monto, "moneda": moneda})
    # AR: donaciones comprometidas no cobradas
    ar = {
        "comprometido": r.randint(5, 20) * 100_000,
        "vencido": r.randint(0, 6) * 100_000,
    }

    # Donacion internacional en USD (muestra de consolidacion FX a cierre)
    grant_usd = 0
    if tier in ("A", "C"):
        grant_usd = r.choice([15_000, 25_000, 40_000])

    # --- Conciliacion fondeo (cross-sistema) y scope de Salesforce ---
    # donaciones_periodo es el mismo hecho economico que reportan los dos sistemas:
    # Salesforce lo reconoce como donacion y NetSuite lo postea como ingreso en el GL.
    # En un mes limpio atan 1:1; la orquestacion lo concilia (ata a ~0 o marca un quiebre).
    # Estos draws van al FINAL: no mueven ningun numero existente.
    donaciones_periodo = r.randint(20, 80) * 100_000
    campanias = r.randint(2, 9)
    voluntarios = r.randint(15, 140)

    return {
        "ong": o, "tier": tier,
        "caja": caja, "gasto_programa": gasto_programa, "gasto_admin": gasto_admin,
        "gasto_mensual": gasto_mensual, "fondos": fondos, "ap": ap,
        "donantes": donantes, "ar": ar, "grant_usd": grant_usd,
        "donaciones_periodo": donaciones_periodo,
        "campanias": campanias, "voluntarios": voluntarios,
    }


def datos_ong(ong_id):
    """La lectura del operating model: compone las dos fuentes de solo lectura.

    NetSuite aporta el bloque contable; Salesforce el de fondeo (con la PII
    segregada en su conector). Una ONG sin un sistema no expone ese bloque: la
    cobertura parcial es honesta, no se inventa un numero para tapar el sistema
    que falta. Mismos numeros que el backing store; la composicion es la novedad."""
    # Import diferido: evita el ciclo finance_core <-> connectors al cargar el modulo.
    from connectors import netsuite, salesforce

    o = get_ong(ong_id)
    tier = o["tier"]
    d = {"ong": o, "tier": tier}
    if tier in ("A", "B"):
        d.update(netsuite.pull(ong_id))      # bloque contable (NetSuite, solo lectura)
    if tier in ("A", "C"):
        d.update(salesforce.pull(ong_id))    # bloque fondeo (Salesforce, solo lectura)
    # Claves que algun consumidor lee aunque el sistema no este conectado (valor neutro).
    d.setdefault("grant_usd", 0)
    d.setdefault("donantes", [])
    d.setdefault("ar", {"comprometido": 0, "vencido": 0})
    return d


# Tolerancia de la conciliacion de fondeo (1%): un desfasaje de timing chico pasa;
# un quiebre real no. La conciliacion ata a ~0 o se marca como quiebre (nunca se
# afirma una conciliacion que no se calculo).
RECON_TOL_PCT = 0.01


def reconciliacion_fondeo(d):
    """Join de la capa de orquestacion: las donaciones reconocidas en Salesforce
    concilian con el ingreso por donaciones posteado en NetSuite.

    Devuelve None si falta un sistema (no aplica). Si estan los dos, devuelve
    {ok, salesforce, netsuite, diff, tol}: ok es True solo si |diff| <= tol. En un
    mes limpio diff = 0. Las dos cifras vienen de conectores distintos; aca se
    comparan, no se asumen iguales."""
    sf = d.get("donaciones_reconocidas_periodo")
    ns = d.get("ingreso_donaciones_gl")
    if sf is None or ns is None:
        return None
    diff = ns - sf
    tol = round(max(abs(sf), abs(ns)) * RECON_TOL_PCT)
    return {"ok": abs(diff) <= tol, "salesforce": sf, "netsuite": ns, "diff": diff, "tol": tol}


# --------------------------------------------------------------------------
# Calculos deterministicos (los indicadores)
# --------------------------------------------------------------------------
def runway_meses(d):
    """Meses de caja: caja / burn neto mensual. Cruza gasto (NetSuite) con fondeo recurrente (Salesforce)."""
    fondeo_recurrente = sum(x["monto_ars"] for x in d["donantes"]) / 6.0  # promedio mensual aprox
    burn_neto = max(d["gasto_mensual"] - fondeo_recurrente, d["gasto_mensual"] * 0.25)
    return d["caja"] / burn_neto


def forecast_caja_semanal(d, semanas=13):
    """Proyeccion semanal cruzando timing de donaciones (entradas) y pagos (salidas)."""
    r = _rng(d["ong"]["id"] + "-fc")
    saldo = d["caja"]
    filas = []
    hoy = date.today()
    entrada_media = sum(x["monto_ars"] for x in d["donantes"]) / 6.0 / 4.3   # semanal aprox
    salida_media = d["gasto_mensual"] / 4.3
    for w in range(1, semanas + 1):
        # donaciones llegan irregulares; pagos de sueldos concentrados a fin de mes
        entrada = entrada_media * r.uniform(0.3, 1.9)
        salida = salida_media * (1.8 if w % 4 == 0 else r.uniform(0.6, 1.1))
        saldo = saldo + entrada - salida
        filas.append({
            "semana": f"S{w}",
            "fecha": (hoy + timedelta(weeks=w)).isoformat(),
            "entradas": round(entrada),
            "salidas": round(salida),
            "saldo_proyectado": round(saldo),
        })
    return filas


def ejecucion_fondos(d):
    out = []
    for f in d["fondos"]:
        pct = f["ejecutado"] / f["presupuesto"] if f["presupuesto"] else 0
        out.append({**f, "ejecucion_pct": pct})
    return out


def uso_restringidos(d):
    rest = [f for f in d["fondos"] if f["tipo"] == "restringido"]
    pres = sum(f["presupuesto"] for f in rest)
    ejec = sum(f["ejecutado"] for f in rest)
    sobre = [f["fondo"] for f in rest if f["ejecutado"] > f["presupuesto"]]
    return {"presupuesto": pres, "ejecutado": ejec, "fondos_sobre_ejecutados": sobre}


def concentracion_donantes(d):
    montos = sorted((x["monto_ars"] for x in d["donantes"]), reverse=True)
    total = sum(montos) or 1
    top3 = sum(montos[:3])
    return top3 / total


def ratio_programa_admin(d):
    total = d["gasto_programa"] + d["gasto_admin"]
    return d["gasto_programa"] / total if total else 0


def gates_aplicables(d):
    """Gates deterministicos filtrados por nivel de dato: cada control se evalua solo
    si la ONG tiene los sistemas que ese control necesita. Asi una ONG solo en
    Salesforce no arrastra un gate contable (NetSuite) que no le corresponde."""
    tier = d["tier"]
    has_contable = tier in ("A", "B")
    has_fondeo = tier in ("A", "C")
    gates = []
    # Cross-sistema: solo tiene sentido con ambos sistemas conectados (A). El
    # resultado se CALCULA (conciliacion real), no se afirma.
    if tier == "A":
        rec = reconciliacion_fondeo(d)
        gates.append(("Donaciones (Salesforce) concilian con ingresos en NetSuite",
                      bool(rec and rec["ok"])))
    # Contable (NetSuite): foot de fondos + segregacion de restringidos.
    if has_contable:
        foot = all(f["presupuesto"] >= 0 for f in d["fondos"])
        gates.append(("Saldos de fondos cuadran (foot)", foot))
        ur = uso_restringidos(d)
        seg_ok = len(ur["fondos_sobre_ejecutados"]) == 0
        gates.append(("Segregacion de fondos restringidos sostenida", seg_ok))
    # Fondeo (Salesforce): etiquetado de donaciones.
    if has_fondeo:
        gates.append(("Donaciones etiquetadas por proyecto/campania en Salesforce", True))
    return gates


def indicadores(d):
    """Set de indicadores disponible segun el tier de datos de la ONG."""
    tier = d["tier"]
    ind = {}
    # Bloque ambos sistemas (A)
    if tier == "A":
        ind["Runway (meses de caja)"] = round(runway_meses(d), 1)
        ind["Uso de fondos restringidos"] = uso_restringidos(d)
        ind["% fondeo en top 3 donantes"] = round(concentracion_donantes(d), 2)
    # Bloque contable (A y B)
    if tier in ("A", "B"):
        ind["% en programa"] = round(ratio_programa_admin(d), 2)
        ej = ejecucion_fondos(d)
        ind["% ejecutado en proyecto"] = round(sum(f["ejecucion_pct"] for f in ej) / len(ej), 2)
        if tier == "B":
            # sin Salesforce, runway estimado solo desde posicion de caja
            ind["Runway (estimado, solo caja)"] = round(d["caja"] / d["gasto_mensual"], 1)
    # Bloque fondeo (A y C)
    if tier in ("A", "C"):
        ind["% fondeo en top 3 donantes"] = round(concentracion_donantes(d), 2)
        ind["Donantes activos"] = len(d["donantes"])
    return ind


def escalaciones(d):
    esc = []
    tier = d["tier"]
    if tier == "A":
        rw = runway_meses(d)
        if rw < RUNWAY_CRITICO:
            esc.append(("CRITICO", f"Runway de {rw:.1f} meses, por debajo del umbral de {RUNWAY_CRITICO:.0f}."))
        elif rw < RUNWAY_ALERTA:
            esc.append(("ALTO", f"Runway de {rw:.1f} meses, en zona de alerta."))
    if tier in ("A", "B"):
        ur = uso_restringidos(d)
        if ur["fondos_sobre_ejecutados"]:
            esc.append(("ALTO", "Fondo restringido sobre-ejecutado: " + ", ".join(ur["fondos_sobre_ejecutados"]) + "."))
    if tier in ("A", "C"):
        c = concentracion_donantes(d)
        if c > CONCENTRACION_ALERTA:
            esc.append(("MEDIO", f"Concentracion de donantes alta: {c*100:.0f}% en los principales."))
        if d["ar"]["vencido"] > 0:
            esc.append(("MEDIO", f"Rendicion / cobro vencido por {_money(d['ar']['vencido'])}."))
    return esc


# --------------------------------------------------------------------------
# Narrativas templadas (en la version viva las escribe el modelo)
# --------------------------------------------------------------------------
def narrativa_caja(d):
    if d["tier"] == "C":
        return "Esta ONG esta solo en Salesforce: no hay dato contable para proyectar caja. Se muestran indicadores de fondeo."
    fc = forecast_caja_semanal(d)
    minimo = min(f["saldo_proyectado"] for f in fc)
    rw = runway_meses(d) if d["tier"] == "A" else d["caja"] / d["gasto_mensual"]
    alerta = " Hay semanas con saldo en descenso; conviene adelantar cobranza de donaciones comprometidas." if minimo < d["caja"] * 0.4 else ""
    return (f"La ONG proyecta del orden de {rw:.1f} meses de caja. En el horizonte de 13 semanas, "
            f"el saldo minimo proyectado es {_money(minimo)}.{alerta}")


def narrativa_reporte(d):
    tier = d["tier"]
    partes = []
    if tier in ("A", "B"):
        rpa = ratio_programa_admin(d) * 100
        partes.append(f"El {rpa:.0f}% del gasto va a programa.")
        ej = ejecucion_fondos(d)
        media = sum(f["ejecucion_pct"] for f in ej) / len(ej) * 100
        partes.append(f"La ejecucion presupuestaria media es del {media:.0f}%.")
    if tier == "A":
        ur = uso_restringidos(d)
        cumple = "sin desvios" if not ur["fondos_sobre_ejecutados"] else "con un fondo restringido sobre-ejecutado"
        partes.append(f"El uso de fondos restringidos cierra {cumple}.")
    if tier in ("A", "C"):
        partes.append(f"El fondeo proviene de {len(d['donantes'])} donantes; "
                      f"los principales concentran el {concentracion_donantes(d)*100:.0f}%.")
    if d["grant_usd"]:
        partes.append(f"Incluye un aporte internacional de USD {d['grant_usd']:,} consolidado a tipo de cambio de cierre "
                      f"({_money(d['grant_usd']*FX_CIERRE['USD'])}).")
    return " ".join(partes)


# --------------------------------------------------------------------------
# Vista programa: agregacion cross-ONG sobre ~50 ONG sinteticas
# --------------------------------------------------------------------------
def universo_programa(n=50):
    """Genera ~50 ONG sinteticas con runway, tier y ejecucion para la vista de cartera."""
    rng = random.Random("potenciar-programa")
    filas = []
    tiers = ["A"] * 30 + ["B"] * 12 + ["C"] * 8   # ~50, mayoria con ambos sistemas
    rng.shuffle(tiers)
    for i in range(n):
        tier = tiers[i]
        runway = round(rng.uniform(1.5, 18.0), 1) if tier != "C" else None
        ejec = round(rng.uniform(0.4, 1.05), 2) if tier in ("A", "B") else None
        filas.append({
            "ong": f"ONG {i+1:02d}", "tier": tier,
            "runway": runway, "ejecucion": ejec,
            "completitud": {"A": 1.0, "B": 0.6, "C": 0.5}[tier],
        })
    return filas


def resumen_programa():
    u = universo_programa()
    con_runway = [x for x in u if x["runway"] is not None]
    en_riesgo = [x for x in con_runway if x["runway"] < RUNWAY_CRITICO]
    alerta = [x for x in con_runway if RUNWAY_CRITICO <= x["runway"] < RUNWAY_ALERTA]
    por_tier = {t: len([x for x in u if x["tier"] == t]) for t in ("A", "B", "C")}
    buckets = {"< 3 meses": len(en_riesgo),
               "3 a 6 meses": len(alerta),
               "> 6 meses": len([x for x in con_runway if x["runway"] >= RUNWAY_ALERTA])}
    return {
        "total": len(u),
        "por_tier": por_tier,
        "en_riesgo": len(en_riesgo),
        "buckets": buckets,
        "universo": u,
    }
