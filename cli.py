"""
cli.py  -  Correr el operating model de punta a punta desde la terminal.

  python cli.py                 # corre una ONG (manos), auto-firma (replay)
  python cli.py raices          # corre otra ONG
  python cli.py --all           # corre las ~6 ONG nombradas

Auto-firma porque no hay humano en la consola (CI/replay): cada firma queda
registrada como 'auto', nunca como una firma humana. La firma real, por etapa, se
hace en la app Streamlit.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

os.environ.setdefault("POTENCIAR_AUTO_APPROVE", "1")

import finance_core_potenciar as fc
import potenciar_orchestrator as orch
import review


def correr(ong_id):
    ctx = orch.run(ong_id)
    s = review.summary(ctx)
    return ctx, s


def main(argv):
    if "--all" in argv:
        for o in fc.ONGS:
            print()
            correr(o["id"])
        return
    ong_id = next((a for a in argv[1:] if not a.startswith("-")), "manos")
    if fc.get_ong(ong_id) is None:
        print(f"ONG desconocida: {ong_id}. Opciones: {[o['id'] for o in fc.ONGS]}")
        sys.exit(1)
    correr(ong_id)


if __name__ == "__main__":
    main(sys.argv)
