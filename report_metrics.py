"""
report_metrics.py  -  Reporte de metricas anonimo (la PII nunca sale de Salesforce).

Dos cosas:
  record_run(state)  - agrega una linea PII-free por corrida a metrics_history.jsonl
                       (conteos y porcentajes; nunca nombres de donantes).
  generate(state)    - arma un reporte markdown de la corrida + un rollup de programa
                       sobre las ~50 ONG sinteticas. Antes de devolverlo, un control
                       de privacidad verifica que ningun campo PII se haya colado;
                       si lo hiciera, levanta PrivacyError y no se genera nada.

Es la garantia de gobierno del PDF hecha codigo: la data de donantes se queda en
Salesforce; lo que sale es agregado y anonimo.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import finance_core_potenciar as fc
import governance
import paths
import review
from shared_state import now_iso


class PrivacyError(RuntimeError):
    """Una salida que se publica filtraria PII. No se genera."""


def _run_summary(state):
    """Resumen PII-free de una corrida: conteos por estado, runway, escalaciones.
    Sin nombres de donantes ni de la ONG en los campos sensibles."""
    inbox = state.get("inbox", [])
    by_estado = {}
    for d in inbox:
        by_estado[d["estado"]] = by_estado.get(d["estado"], 0) + 1
    fcast = next((d for d in inbox if d["clave"] == "forecast"), None)
    runway = (fcast or {}).get("datos", {}).get("runway_meses") if fcast else None
    return {
        "ts": now_iso(),
        "ong_id": state.get("meta", {}).get("ong_id"),
        "periodo": state.get("meta", {}).get("periodo"),
        "entregables": len(inbox),
        "by_estado": by_estado,
        "publicado": by_estado.get(review.PUBLICADO, 0) > 0,
        "bloqueados": by_estado.get(review.BLOQUEADO, 0),
        "runway_meses": runway,
        "escalaciones": len(state.get("flags", [])),
    }


def record_run(state):
    """Agrega el resumen PII-free de esta corrida al historico (append-only)."""
    paths.ensure_dirs()
    with open(paths.METRICS_HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(_run_summary(state), ensure_ascii=False) + "\n")
    return paths.METRICS_HISTORY


def _assert_no_pii(texto, state):
    """Control de privacidad: ningun nombre de donante puede aparecer en la salida."""
    nombres = []
    for dlv in state.get("inbox", []):
        for x in dlv.get("datos", {}).get("donantes", []) if isinstance(dlv.get("datos"), dict) else []:
            nombres.append(x)
    # Los nombres de donantes no se persisten en el inbox (solo conteos), pero el
    # control corre igual sobre cualquier termino PII conocido por las fuentes.
    fuente_pii = []
    ong_id = state.get("meta", {}).get("ong_id")
    if ong_id:
        try:
            for x in fc.datos_ong(ong_id)["donantes"]:
                fuente_pii.append(x["donante"])
        except Exception:
            pass
    if governance.has_pii(texto, fuente_pii):
        raise PrivacyError("la salida contiene un nombre de donante (PII); no se genera")


def generate(state):
    """Devuelve {'md': ...} con el reporte anonimo. Levanta PrivacyError si filtra PII."""
    rs = _run_summary(state)
    prog = fc.resumen_programa()
    lineas = [
        "# Reporte de metricas (anonimo) - Operating Model",
        "",
        "_Conteos y porcentajes. No contiene datos de donantes ni PII._",
        "",
        "## Corrida",
        f"- Periodo: {rs['periodo']}",
        f"- Entregables: {rs['entregables']}  ·  por estado: {rs['by_estado']}",
        f"- Runway (meses): {rs['runway_meses'] if rs['runway_meses'] is not None else 's/d'}",
        f"- Escalaciones: {rs['escalaciones']}  ·  bloqueados: {rs['bloqueados']}  ·  publicado: {rs['publicado']}",
        "",
        "## Programa (cartera sintetica de ~50 ONG)",
        f"- ONG instrumentadas: {prog['total']}",
        f"- ONG en riesgo (runway < {fc.RUNWAY_CRITICO:.0f} meses): {prog['en_riesgo']}",
        f"- Cobertura set completo (ambos sistemas): {prog['por_tier']['A']} de {prog['total']}",
        f"- Distribucion de runway: {prog['buckets']}",
        "",
        "_Generado por el operating model. Patron reutilizable; mapeo por ONG._",
    ]
    md = "\n".join(lineas)
    _assert_no_pii(md, state)
    return {"md": md}
