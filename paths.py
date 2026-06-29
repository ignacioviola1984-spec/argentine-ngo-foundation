"""
paths.py  -  Rutas canonicas del operating model (una sola fuente de verdad).

Cada modulo deriva sus rutas de aca, asi el estado compartido, la traza
append-only (el "log de sesion" de la capa de gobierno) y el registro de activos
de IA nunca se escriben dos veces. paths.py vive en la raiz del repo, asi que
REPO_ROOT es la raiz de ESTE repo y el .env con ANTHROPIC_API_KEY se espera en
<repo>/.env (solo se usa cuando se activa la redaccion con el modelo).
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))          # raiz del repo (paths.py vive aca)
REPO_ROOT = HERE
ENV_PATH = os.path.join(REPO_ROOT, ".env")                 # <repo>/.env (ANTHROPIC_API_KEY)

OUTPUTS_DIR = os.path.join(HERE, "outputs")
AI_ASSETS_DIR = os.path.join(HERE, "ai_assets")            # registro de activos de IA (versionado, commiteado)

STATE_PATH = os.path.join(HERE, "potenciar_state.json")    # persistencia del PotenciarContext
AUDIT_PATH = os.path.join(HERE, "audit_log.jsonl")         # traza append-only (log de sesion)
METRICS_HISTORY = os.path.join(OUTPUTS_DIR, "metrics_history.jsonl")  # metricas anonimas por corrida


def ensure_dirs():
    """Crea outputs/ si no existe. ai_assets/ se versiona y ya existe en el repo."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
