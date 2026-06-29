"""
governance.py  -  La capa de gobierno y trazabilidad del operating model, en codigo.

El PDF declara cuatro garantias de gobierno; aca dejan de ser una promesa de slide
y pasan a ser invariantes que el codigo sostiene:

  1. Solo lectura      - NetSuite y Salesforce se leen, nunca se escriben. Los
                         conectores solo devuelven datos; no existe una ruta de
                         escritura a los sistemas de registro.
  2. Datos de donantes - la PII (nombres de donantes, contacto) nunca sale hacia
                         una salida agregada o de programa. `redact()` y el control
                         de privacidad del reporte de metricas lo hacen cumplir.
  3. Registro de activos IA - prompts versionados + golden outputs + rubrica
                         viven en ai_assets/ (versionado). Es lo reutilizable.
  4. Log de sesion     - traza append-only (fecha, inputs, salida, revisor) en
                         shared_state -> audit_log.jsonl.

Segregacion por ONG: cada conexion y cada salida quedan namespaced por ong_id, asi
la data de una ONG nunca se mezcla con la de otra.
"""

# La IA opera en solo lectura sobre los sistemas de registro. Es una constante,
# no una opcion: ningun agente ni conector tiene una ruta de escritura.
READ_ONLY = True

# Campos PII que viven en Salesforce y NO deben salir hacia una vista de programa
# ni hacia el reporte de metricas anonimo.
PII_FIELDS = ("donante", "email", "telefono", "nombre_contacto")

# Sistemas de registro y su modo de acceso (solo lectura, scope minimo).
SISTEMAS = {
    "salesforce": {"rol": "fondeo", "acceso": "solo_lectura", "pii": True,
                   "scope": "donantes, donaciones, campanias, voluntarios"},
    "netsuite":   {"rol": "contable", "acceso": "solo_lectura", "pii": False,
                   "scope": "plan de cuentas, gastos, proveedores, AP/AR"},
}

# Roles humanos del operating model (los del diagrama). El acceso es de solo
# lectura y otorgado por sistema; la ONG controla las conexiones y permisos.
ROLES = {
    "operador_hitl": "Ignacio Viola (consultor) - disena, opera y firma cada salida (human-in-the-loop)",
    "gatekeeper":    "NGO-side operations owner - controla las conexiones y los permisos (acceso por sistema)",
    "soporte_netsuite": "NetSuite implementation/support partners - soporte tecnico de la integracion NetSuite",
}


class ReadOnlyViolation(RuntimeError):
    """Se intento escribir en un sistema de registro. Nunca debe ocurrir."""


def assert_read_only(sistema: str, accion: str = "write"):
    """Punto de control unico. Cualquier intento de escritura a un sistema de
    registro corta aca. Los conectores solo llaman a esto con 'read'."""
    if accion != "read":
        raise ReadOnlyViolation(
            f"La IA no escribe en los sistemas de registro: intento '{accion}' en {sistema}. "
            "El operating model es solo lectura (capa de gobierno)."
        )
    return True


def redact(registros, pii_fields=PII_FIELDS):
    """Devuelve copias de los registros sin los campos PII. Se usa cuando un dato
    de donante tiene que cruzar hacia una salida agregada: la PII se queda atras."""
    out = []
    for r in registros:
        out.append({k: v for k, v in r.items() if k not in pii_fields})
    return out


def has_pii(texto: str, nombres) -> bool:
    """True si un texto destinado a una salida anonima filtra un nombre PII."""
    t = (texto or "").lower()
    return any(n and n.lower() in t for n in nombres)
