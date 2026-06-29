"""
review.py  -  La bandeja de aprobacion de entregables (human-in-the-loop, dos niveles).

Cada etapa asistida del operating model produce UN entregable (por ONG por periodo).
El consultor es el revisor. El HITL tiene DOS niveles, como en el refactor del
modelo financiero:

  Nivel 1 (firma por etapa / dominio):  cada entregable arranca `pendiente` y el
     consultor lo aprueba / edita / rechaza individualmente. Un control que no
     cuadra lo deja `bloqueado` (fail-closed): no se firma sobre un gate que falla.

  Nivel 2 (gate final de publicacion):  el reporte a Comision Directiva y donantes
     -el artefacto que sale hacia afuera- solo se PUBLICA cuando el prerrequisito
     (diagnostico) y el forecast ya estan firmados, y el propio reporte esta
     aprobado. Es la firma final del consultor antes de que un numero salga.

Estados:  pendiente -> aprobado | editado | rechazado | bloqueado
          (el reporte aprobado puede luego pasar a `publicado` por el gate final)
          no_aplica  (el nivel de dato de la ONG no habilita esta etapa)

Cada decision registra quien / que / cuando (decided_by/revisor, nota, timestamps)
en la traza: la evidencia de control que el patron maker-checker exige.
"""

import os
import sys
from dataclasses import dataclass, asdict, field, fields
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from shared_state import now_iso

# Estados.
PENDIENTE, APROBADO, EDITADO, RECHAZADO = "pendiente", "aprobado", "editado", "rechazado"
BLOQUEADO, NO_APLICA, PUBLICADO = "bloqueado", "no_aplica", "publicado"
FIRMADO = (APROBADO, EDITADO, PUBLICADO)         # entregables con firma de dominio
PUBLICABLE_DESDE = (APROBADO, EDITADO)            # estados desde los que se puede publicar

REVISOR = "Ignacio Viola (consultor, HITL)"       # el unico firmante


@dataclass
class Deliverable:
    """Un entregable de una etapa, esperando la decision del consultor.

    `datos` lleva los numeros deterministicos detras del entregable (las cifras que
    la narrativa puede citar); el guarda de grounding la chequea contra esto.
    `gates` son los controles deterministicos (texto, ok): si alguno es False, el
    entregable nace bloqueado. `narrativa_propuesta` es prosa redactada;
    `narrativa_final` es lo que se publica (la propuesta salvo que el consultor edite)."""
    id: str
    etapa_n: int
    clave: str                 # diagnostico | forecast | reporte | cierre | dashboards
    titulo: str
    fase: str                  # PRERREQUISITO | CONSTRUIDA
    agente: str
    ong_id: str
    ong_nombre: str
    periodo: str
    tier: str
    detalle: str               # resumen deterministico legible
    datos: dict                # payload deterministico (numeros detras del entregable)
    gates: list = field(default_factory=list)        # [[texto, ok], ...]
    narrativa_propuesta: str = ""
    publicable: bool = False   # True solo para el reporte (artefacto externo, gate nivel 2)
    estado: str = PENDIENTE
    narrativa_final: Optional[str] = None
    decision_note: str = ""
    decided_by: Optional[str] = None
    ts_creada: str = field(default_factory=now_iso)
    ts_decidida: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def make_id(clave, ong_id, periodo):
    """Id estable y unico (asi re-corridas/replay producen ids identicos)."""
    return f"{clave}|{ong_id}|{periodo}"


def gates_ok(d) -> bool:
    """True si todos los controles deterministicos del entregable cuadran."""
    return all(ok for _, ok in d.get("gates", []))


# --------------------------------------------------------------------------
# Operaciones sobre la bandeja (state["inbox"]).
# --------------------------------------------------------------------------

def add_deliverable(ctx, dlv: Deliverable):
    """Un agente (maker) somete un entregable. Entra `pendiente`, salvo que un
    control falle: entonces nace `bloqueado` (fail-closed)."""
    if dlv.estado == PENDIENTE and dlv.gates and not gates_ok(dlv.to_dict()):
        dlv.estado = BLOQUEADO
    ctx.state["inbox"].append(dlv.to_dict())
    estado_msg = "BLOQUEADO (un control no cuadra)" if dlv.estado == BLOQUEADO else "pendiente"
    ctx.audit(dlv.agente, "PROPUESTA",
              f"etapa {dlv.etapa_n} · {dlv.titulo} · {dlv.ong_nombre} · {estado_msg}")
    return dlv.id


def _find(ctx, dlv_id):
    for d in ctx.state["inbox"]:
        if d["id"] == dlv_id:
            return d
    raise KeyError(f"entregable no encontrado: {dlv_id}")


def list_deliverables(ctx, estado=None, clave=None):
    out = ctx.state["inbox"]
    if estado is not None:
        out = [d for d in out if d["estado"] == estado]
    if clave is not None:
        out = [d for d in out if d["clave"] == clave]
    return out


def get(ctx, clave):
    for d in ctx.state["inbox"]:
        if d["clave"] == clave:
            return d
    return None


def pending(ctx):
    return list_deliverables(ctx, estado=PENDIENTE)


# -- Nivel 1: firma por etapa --------------------------------------------

def approve(ctx, dlv_id, note="", by=REVISOR):
    """El consultor firma el entregable tal cual. Bloqueado no se puede firmar."""
    d = _find(ctx, dlv_id)
    if d["estado"] == BLOQUEADO:
        raise ValueError("no se puede firmar un entregable bloqueado: corregir el dato primero")
    d["estado"] = APROBADO
    d["narrativa_final"] = d.get("narrativa_final") or d["narrativa_propuesta"]
    d["decision_note"] = note
    d["decided_by"] = by
    d["ts_decidida"] = now_iso()
    ctx.audit(d["agente"], "APROBADO", f"{d['titulo']} · {d['ong_nombre']}"
              + (f" · {note}" if note else ""), revisor=by)
    return d


def edit(ctx, dlv_id, nueva_narrativa, note="", by=REVISOR):
    """El consultor edita la narrativa y la firma (estado = editado)."""
    d = _find(ctx, dlv_id)
    if d["estado"] == BLOQUEADO:
        raise ValueError("no se puede firmar un entregable bloqueado: corregir el dato primero")
    d["estado"] = EDITADO
    d["narrativa_final"] = nueva_narrativa
    d["decision_note"] = note
    d["decided_by"] = by
    d["ts_decidida"] = now_iso()
    ctx.audit(d["agente"], "EDITADO", f"{d['titulo']} · {d['ong_nombre']} · narrativa editada"
              + (f" · {note}" if note else ""), revisor=by)
    return d


def reject(ctx, dlv_id, note="", by=REVISOR):
    """El consultor rechaza el entregable. Queda logueado; no se publica."""
    d = _find(ctx, dlv_id)
    d["estado"] = RECHAZADO
    d["narrativa_final"] = None
    d["decision_note"] = note
    d["decided_by"] = by
    d["ts_decidida"] = now_iso()
    ctx.audit(d["agente"], "RECHAZADO", f"{d['titulo']} · {d['ong_nombre']}"
              + (f" · {note}" if note else ""), revisor=by)
    return d


# -- Nivel 2: gate final de publicacion ----------------------------------

def can_publish(ctx):
    """(ok, faltantes): el reporte solo se publica si el prerrequisito (diagnostico)
    y el forecast (cuando aplica) ya estan firmados, y el reporte esta
    aprobado/editado. Devuelve que falta si no se puede."""
    rep = get(ctx, "reporte")
    faltan = []
    if not rep:
        return False, ["no hay reporte generado"]
    if rep["estado"] not in PUBLICABLE_DESDE:
        faltan.append("el reporte tiene que estar aprobado o editado")
    diag = get(ctx, "diagnostico")
    if not diag or diag["estado"] not in FIRMADO:
        faltan.append("el diagnostico de datos (prerrequisito) tiene que estar firmado")
    fc = get(ctx, "forecast")
    if fc and fc["estado"] not in FIRMADO + (NO_APLICA,):
        faltan.append("el forecast de caja tiene que estar firmado")
    return (len(faltan) == 0), faltan


def publish(ctx, note="", by=REVISOR):
    """Gate final: publica el reporte a CD y donantes. Solo procede si can_publish."""
    ok, faltan = can_publish(ctx)
    if not ok:
        raise ValueError("gate final bloqueado: " + "; ".join(faltan))
    rep = get(ctx, "reporte")
    rep["estado"] = PUBLICADO
    rep["decision_note"] = (rep.get("decision_note", "") + " | publicado: " + note).strip(" |")
    rep["decided_by"] = by
    rep["ts_decidida"] = now_iso()
    ctx.audit("reporte_agent", "PUBLICADO",
              f"Reporte publicado a Comision Directiva y donantes · {rep['ong_nombre']}"
              + (f" · {note}" if note else ""), revisor=by)
    return rep


# --------------------------------------------------------------------------
# Resumen / orden.
# --------------------------------------------------------------------------

def summary(ctx):
    inbox = ctx.state["inbox"]
    by_estado = {}
    for d in inbox:
        by_estado[d["estado"]] = by_estado.get(d["estado"], 0) + 1
    firmados = len([d for d in inbox if d["estado"] in FIRMADO])
    return {
        "total": len(inbox),
        "by_estado": by_estado,
        "pendientes": len(pending(ctx)),
        "bloqueados": by_estado.get(BLOQUEADO, 0),
        "firmados": firmados,
        "publicado": by_estado.get(PUBLICADO, 0) > 0,
    }


def ordenados(ctx):
    """La bandeja completa, en el orden del operating model (por numero de etapa)."""
    return sorted(ctx.state["inbox"], key=lambda d: d["etapa_n"])
