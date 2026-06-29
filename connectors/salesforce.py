"""
connectors/salesforce.py  -  Conector de SOLO LECTURA sobre Salesforce (sistema de fondeo).

Salesforce es el sistema de registro del fondeo: donantes, donaciones, campanias,
voluntarios, AR. Este conector solo LEE: cada llamada pasa por governance.assert_read_only.

Es el UNICO lugar donde existe la PII de donantes (email, telefono, contacto). La
garantia de gobierno del diagrama -"la PII nunca sale de Salesforce"- se sostiene
aca: `pull()` devuelve un bloque SIN PII (nombre de donante y monto, para la vista
operativa del consultor); la PII completa solo se obtiene con `donantes_pii()` y
nunca entra al estado compartido ni a una salida. `governance.redact` la borra
cuando un registro tiene que cruzar a una vista agregada o de programa.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import finance_core_potenciar as fc
import governance

SYSTEM = "salesforce"
ROL = governance.SISTEMAS[SYSTEM]["rol"]
SCOPE = governance.SISTEMAS[SYSTEM]["scope"]


def _slug(nombre):
    """Normaliza un nombre a un identificador simple (para email/contacto sinteticos)."""
    base = "".join(c.lower() if c.isalnum() else "." for c in nombre)
    while ".." in base:
        base = base.replace("..", ".")
    return base.strip(".")


def pull(ong_id):
    """Lee la posicion de fondeo de la ONG desde Salesforce (solo lectura).

    Devuelve el bloque de fondeo que consumen el motor y los agentes. El nombre de
    donante se conserva para la vista operativa del consultor (scope Salesforce); el
    resto de la PII (email, telefono, contacto) NO se incluye: vive solo en este
    conector (`donantes_pii`). Incluye `donaciones_reconocidas_periodo`: el monto de
    donaciones reconocido en el periodo (lado fondeo de la conciliacion)."""
    governance.assert_read_only(SYSTEM, "read")
    s = fc._backing_store(ong_id)
    # Bloque PII-free hacia el estado compartido: nombre + monto + moneda.
    donantes = [{"donante": x["donante"], "monto_ars": x["monto_ars"], "moneda": x["moneda"]}
                for x in s["donantes"]]
    return {
        "donantes": donantes,
        "ar": s["ar"],
        "grant_usd": s["grant_usd"],
        # Donaciones reconocidas en el periodo (lado fondeo de la conciliacion).
        "donaciones_reconocidas_periodo": s["donaciones_periodo"],
        "campanias": s["campanias"],
        "voluntarios": s["voluntarios"],
    }


def donantes_pii(ong_id):
    """Registros completos de donantes CON PII (nombre, email, telefono, contacto).

    Existe SOLO aca, para hacer explicito el limite de segregacion: la PII no entra al
    estado compartido ni a ninguna salida. Para cruzar un registro a una vista
    agregada se pasa por `governance.redact`, que borra los campos PII."""
    governance.assert_read_only(SYSTEM, "read")
    s = fc._backing_store(ong_id)
    out = []
    for x in s["donantes"]:
        slug = _slug(x["donante"])
        out.append({
            "donante": x["donante"], "monto_ars": x["monto_ars"], "moneda": x["moneda"],
            "email": f"{slug}@example.org",
            "telefono": "+54 11 5555 0000",
            "nombre_contacto": f"Referente {x['donante']}",
        })
    return out
