"""
shared_state.py  -  PotenciarContext: el "libro" compartido de una corrida.

Espeja CFOContext / CarteraContext del repo de finanzas, para el dominio de la
ONG. Cada agente put()-ea su resultado estructurado + flags; los pares y el
orquestador lo get()-ean. Cada paso se agrega a la traza de auditoria (en memoria
y al audit_log.jsonl append-only -el "log de sesion" de la capa de gobierno-) y
el estado completo persiste a potenciar_state.json.

Esto es lo que hace la corrida auditable y replayable: quien escribio que, cuando,
y con que revisor. La bandeja de entregables vive en state["inbox"] pero la maneja
review.py (mismo split que en el modelo financiero).
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import paths

# La consola de Windows usa cp1252 por defecto y no imprime los acentos del
# espaniol. Forzamos UTF-8 en stdout/stderr (shared_state lo importa todo el
# pipeline), asi la traza imprime sin romper.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


class PotenciarContext:
    """Estado compartido y persistido de una corrida del operating model."""

    def __init__(self, state_path=None, audit_path=None, fresh_audit=False,
                 ong_id=None, periodo=None):
        self.state_path = state_path or paths.STATE_PATH
        self.audit_path = audit_path or paths.AUDIT_PATH
        self.state = {
            "meta": {"started": now_iso(), "ong_id": ong_id, "periodo": periodo},
            "agents": {},     # agente -> payload de resultado estructurado
            "flags": [],      # [{agent, severity, message, ts}]
            "audit": [],      # [{ts, agent, status, detail, revisor}]
            "inbox": [],      # [Deliverable.to_dict()]  (lo maneja review.py)
        }
        # Arranca una traza nueva para esta corrida cuando se pide (CI/replay);
        # si no, sigue agregando a la traza historica entre corridas.
        if fresh_audit and os.path.exists(self.audit_path):
            os.remove(self.audit_path)

    # -- comunicacion lateral entre agentes ---------------------------
    def put(self, agent, payload):
        """Un agente deja su resultado estructurado en el libro comun."""
        self.state["agents"].setdefault(agent, {}).update(payload)

    def get(self, agent, key=None, default=None):
        a = self.state["agents"].get(agent, {})
        return a if key is None else a.get(key, default)

    # -- flags + auditoria --------------------------------------------
    def flag(self, agent, severity, message):
        self.state["flags"].append(
            {"agent": agent, "severity": severity, "message": message, "ts": now_iso()})
        self.audit(agent, f"FLAG/{severity}", message)

    def audit(self, agent, status, detail, revisor=None):
        """Agrega un paso a la traza: en memoria + jsonl append-only. `revisor`
        registra quien decidio (en los pasos HITL); 'sistema' en los pasos de codigo."""
        evt = {"ts": now_iso(), "agent": agent, "status": status,
               "detail": detail, "revisor": revisor or "sistema"}
        self.state["audit"].append(evt)
        paths.ensure_dirs()
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        return evt

    # -- persistencia -------------------------------------------------
    def save(self):
        # allow_nan=False: si un inf/NaN se cuela en un numero, falla fuerte aca
        # en vez de escribir un JSON invalido que un parser estricto rechazaria.
        self.state["meta"]["saved"] = now_iso()
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2, allow_nan=False)
        return self.state_path

    @classmethod
    def load(cls, state_path=None):
        ctx = cls(state_path=state_path)
        with open(ctx.state_path, encoding="utf-8") as f:
            ctx.state = json.load(f)
        return ctx
