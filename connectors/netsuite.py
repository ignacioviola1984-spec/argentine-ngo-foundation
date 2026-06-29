"""
connectors/netsuite.py  -  Conector de SOLO LECTURA sobre NetSuite (sistema contable).

NetSuite es el sistema de registro contable: plan de cuentas, caja, gasto, fondos,
AP/AR. Este conector solo LEE: cada llamada pasa por governance.assert_read_only y
no existe ninguna ruta de escritura al sistema de registro.

No contiene PII: la data de donantes vive en Salesforce, no aca. Lo unico que cruza
del lado del fondeo es el ingreso por donaciones POSTEADO en el GL (un numero
contable), que la capa de orquestacion concilia contra lo que Salesforce reconocio.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import finance_core_potenciar as fc
import governance

SYSTEM = "netsuite"
ROL = governance.SISTEMAS[SYSTEM]["rol"]
SCOPE = governance.SISTEMAS[SYSTEM]["scope"]


def pull(ong_id):
    """Lee la posicion contable de la ONG desde NetSuite (solo lectura).

    Devuelve el bloque contable que consumen el motor y los agentes. Incluye
    `ingreso_donaciones_gl`: el ingreso por donaciones posteado en el libro mayor
    del periodo, que la orquestacion concilia contra Salesforce. Sin PII."""
    governance.assert_read_only(SYSTEM, "read")
    s = fc._backing_store(ong_id)
    return {
        "caja": s["caja"],
        "gasto_programa": s["gasto_programa"],
        "gasto_admin": s["gasto_admin"],
        "gasto_mensual": s["gasto_mensual"],
        "fondos": s["fondos"],
        "ap": s["ap"],
        # Ingreso por donaciones posteado en el GL (lado contable de la conciliacion).
        "ingreso_donaciones_gl": s["donaciones_periodo"],
        # Posicion de caja segun NetSuite (la usa el gate del forecast).
        "posicion_caja_netsuite": s["caja"],
    }
