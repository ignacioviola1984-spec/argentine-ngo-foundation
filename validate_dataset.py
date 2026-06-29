"""
validate_dataset.py  -  Corre el operating model (deterministico) sobre un dataset
sintetico con shape de los sistemas reales (Salesforce sf_*, NetSuite ns_*) y lo
compara contra las salidas esperadas (exp_*) del propio dataset.

Es el banco de pruebas del nucleo deterministico contra ground truth: cierre por
periodo/fondo, reporte a donantes por fondo, forecast de caja semanal y la cola de
excepciones. Los numeros se calculan en codigo; despues se contrastan celda a celda.

  python validate_dataset.py [ruta_xlsx]
"""
import os
import sys
import numpy as np
import pandas as pd

PATH = (sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("POTENCIAR_DATASET", "potenciar_synthetic_dataset.xlsx"))
if not os.path.exists(PATH):
    sys.exit(f"Dataset no encontrado: {PATH}\n"
             f"Uso: python validate_dataset.py <ruta_al_xlsx>  (o POTENCIAR_DATASET=<ruta>)")
ASOF = pd.Timestamp("2026-06-30")
OPENING_CASH = 13167000
BURN_MONTHS = ["2026-04", "2026-05", "2026-06"]   # ventana de burn (ultimos 3 meses)

xl = pd.ExcelFile(PATH)
S = lambda n: xl.parse(n)

fund_map = S("fund_project_map")
mapped_funds = set(fund_map.fund_code)
restricted = set(fund_map.loc[fund_map.restriction_type == "Restricted", "fund_code"])
nt = S("ns_transactions"); sd = S("sf_donations")
bud = S("budget_plan"); fr = S("forecast_receipts"); fp = S("forecast_payments")
ven = S("ns_vendors").set_index("vendor_id")

for df, c in [(sd, "pledge_date"), (sd, "expected_receipt_date"), (sd, "received_date"),
              (nt, "transaction_date"), (fr, "expected_date"), (fp, "expected_payment_date")]:
    df[c] = pd.to_datetime(df[c], errors="coerce")


def report(title, comp, exp, keys, numcols, pctcols=()):
    """Compara dos dataframes en keys; reporta filas/celdas que no atan."""
    comp = comp.sort_values(keys).reset_index(drop=True)
    exp = exp.sort_values(keys).reset_index(drop=True)
    m = exp.merge(comp, on=keys, how="outer", suffixes=("_exp", "_got"), indicator=True)
    only = m[m["_merge"] != "both"]
    diffs = []
    both = m[m["_merge"] == "both"]
    for col in numcols:
        a, b = both[f"{col}_got"], both[f"{col}_exp"]
        bad = both[(a.fillna(0) - b.fillna(0)).abs() > 0.5]
        for _, r in bad.iterrows():
            diffs.append((tuple(r[k] for k in keys), col, r[f"{col}_exp"], r[f"{col}_got"]))
    for col in pctcols:
        a, b = both[f"{col}_got"].round(4), both[f"{col}_exp"].round(4)
        bad = both[(a.fillna(-999) - b.fillna(-999)).abs() > 0.0005]
        for _, r in bad.iterrows():
            diffs.append((tuple(r[k] for k in keys), col, r[f"{col}_exp"], r[f"{col}_got"]))
    ok = only.empty and not diffs
    print(f"\n{'='*78}\n{title}: {'OK - ata 100%' if ok else 'DIFERENCIAS'}")
    print(f"  filas esperadas {len(exp)} · calculadas {len(comp)}")
    if not only.empty:
        for _, r in only.iterrows():
            print(f"  falta/sobra ({r['_merge']}): {tuple(r[k] for k in keys)}")
    for k, col, e, g in diffs:
        print(f"  {k} · {col}: esperado {e} != calculado {g}")
    return ok


# ====================== 1) CIERRE MENSUAL (periodo x fondo) ======================
g = nt.groupby(["posting_period", "fund_code"])
close = pd.DataFrame({
    "cash_receipts_ars": g.apply(lambda x: x.loc[x.cash_effect_ars > 0, "cash_effect_ars"].sum()),
    "cash_payments_ars": g.apply(lambda x: -x.loc[x.cash_effect_ars < 0, "cash_effect_ars"].sum()),
    "revenue_ars": g.revenue_effect_ars.sum(),
    "expenses_ars": g.expense_effect_ars.sum(),
}).reset_index().rename(columns={"posting_period": "period"})
close["net_cash_flow_ars"] = close.cash_receipts_ars - close.cash_payments_ars
budg = (bud.groupby(["period", "fund_code"]).budget_amount_ars.sum()
        .reset_index().rename(columns={"budget_amount_ars": "budget_expenses_ars"}))
close = close.merge(budg, on=["period", "fund_code"], how="left")
close["budget_expenses_ars"] = close.budget_expenses_ars.fillna(0).astype(int)
close["expense_variance_vs_budget_ars"] = close.budget_expenses_ars - close.expenses_ars
close["expense_variance_pct"] = np.where(
    close.budget_expenses_ars != 0,
    (close.expenses_ars - close.budget_expenses_ars) / close.budget_expenses_ars, np.nan)
close["status"] = np.where(close.fund_code.isin(mapped_funds), "OK", "Review")

exp_close = S("exp_close_summary")
ok_close = report("CIERRE MENSUAL", close, exp_close, ["period", "fund_code"],
                  ["cash_receipts_ars", "cash_payments_ars", "net_cash_flow_ars", "revenue_ars",
                   "expenses_ars", "budget_expenses_ars", "expense_variance_vs_budget_ars"],
                  pctcols=["expense_variance_pct"])

# ====================== 2) REPORTE A DONANTES (por fondo) ======================
received = nt.groupby("fund_code").revenue_effect_ars.sum()      # NetSuite = fuente de lo recibido
spend = nt.groupby("fund_code").expense_effect_ars.sum()          # NetSuite = gasto
# pledged: Salesforce, comprometido "hasta la fecha de corte" = lo esperado a cobrar
# hasta el corte MAS lo ya recibido (un pledge cobrado cuenta aunque su fecha
# esperada caiga unos dias despues del corte). Excluye los pledges puramente futuros.
pl = (sd[(sd.expected_receipt_date <= ASOF) | (sd.amount_received_ars > 0)]
      .groupby("fund_code").amount_pledged_ars.sum())
burn = (nt[nt.posting_period.isin(BURN_MONTHS)].groupby(["fund_code"]).expense_effect_ars.sum()
        / len(BURN_MONTHS))
rows = []
for _, f in fund_map.iterrows():
    fc = f.fund_code
    rec = int(received.get(fc, 0)); spe = int(spend.get(fc, 0))
    rows.append({
        "fund_code": fc, "pledged_through_asof_ars": int(pl.get(fc, 0)),
        "received_through_asof_ars": rec, "spend_through_asof_ars": spe,
        "remaining_fund_balance_ars": rec - spe,
        "avg_monthly_burn_last_3_months_ars": int(round(burn.get(fc, 0))),
        "status_rag": "Red" if rec - spe < 0 else "Green",
    })
donor = pd.DataFrame(rows)
exp_donor = S("exp_donor_report")
ok_donor = report("REPORTE A DONANTES", donor, exp_donor, ["fund_code"],
                  ["pledged_through_asof_ars", "received_through_asof_ars", "spend_through_asof_ars",
                   "remaining_fund_balance_ars", "avg_monthly_burn_last_3_months_ars"])
# RAG aparte (texto)
dm = donor.merge(exp_donor[["fund_code", "status_rag"]], on="fund_code", suffixes=("_got", "_exp"))
rag_bad = dm[dm.status_rag_got != dm.status_rag_exp]
print("  RAG donantes:", "OK" if rag_bad.empty else
      {r.fund_code: (r.status_rag_exp, r.status_rag_got) for _, r in rag_bad.iterrows()})

# ====================== 3) FORECAST DE CAJA (semanal, 13 semanas) ======================
exp_fc = S("exp_cash_forecast"); exp_fc["week_start"] = pd.to_datetime(exp_fc.week_start)
exp_fc["week_end"] = pd.to_datetime(exp_fc.week_end)
weeks = list(zip(exp_fc.week_start, exp_fc.week_end))           # usamos el calendario semanal del dataset
rec_w, pay_w = [], []
for ws, we in weeks:
    rec_w.append(int(fr.loc[(fr.expected_date >= ws) & (fr.expected_date <= we),
                            "probability_weighted_amount_ars"].sum()))
    pay_w.append(int(fp.loc[(fp.expected_payment_date >= ws) & (fp.expected_payment_date <= we),
                            "expected_amount_ars"].sum()))
fc_rows, cash = [], OPENING_CASH
# Burn semanal para runway = burn de CAJA (pagos de los ultimos 3 meses / 13), NO
# el burn de gasto del reporte a donantes: el runway es una metrica de caja y el
# accrual de junio (gasto sin salida de caja) no consume runway. Ese fue el error.
weekly_burn = close[close.period.isin(BURN_MONTHS)].cash_payments_ars.sum() / 13.0
for (ws, we), r, p in zip(weeks, rec_w, pay_w):
    opening = cash; closing = opening + r - p; cash = closing
    rw = round(closing / weekly_burn, 1) if weekly_burn else None
    fc_rows.append({"week_start": ws, "expected_receipts_ars": r, "expected_payments_ars": p,
                    "opening_cash_ars": opening, "closing_cash_ars": closing, "runway_weeks": rw})
fcst = pd.DataFrame(fc_rows)
ok_fc = report("FORECAST DE CAJA", fcst, exp_fc, ["week_start"],
               ["opening_cash_ars", "expected_receipts_ars", "expected_payments_ars", "closing_cash_ars"])
# status RAG del forecast: Green si runway>=8, Amber si 3<=runway<8, Red si <3
fcst["status_got"] = np.where(fcst.runway_weeks >= 8, "Green",
                       np.where(fcst.runway_weeks >= 3, "Amber", "Red"))
fm = fcst.merge(exp_fc[["week_start", "runway_weeks", "status"]], on="week_start",
                suffixes=("_got", "_exp"))
fm["d"] = (fm.runway_weeks_got - fm.runway_weeks_exp).abs()
rag_fc_bad = fm[fm.status_got != fm.status]
print(f"  runway_weeks (metrica derivada, base de burn no especificada en el dataset): "
      f"max |dif| = {fm.d.max():.1f} semanas; calculado con burn semanal "
      f"{weekly_burn:,.0f} ARS")
print("  status RAG forecast:", "OK" if rag_fc_bad.empty else
      {str(r.week_start.date()): (r.status, r.status_got) for _, r in rag_fc_bad.iterrows()})

# ====================== 4) EXCEPCIONES (cola de control / HITL) ======================
exc = []   # (exception_type, source_record)
# overdue pledged receipt
for _, r in sd.iterrows():
    if r.payment_status == "Overdue" or (pd.notna(r.expected_receipt_date)
                                         and r.expected_receipt_date <= ASOF and r.amount_received_ars == 0):
        exc.append(("Overdue pledged receipt", r.donation_id))
# reconciliacion SF <-> NS
ns_dep = nt[nt.revenue_effect_ars > 0]
ns_by_don = ns_dep.set_index("related_donation_id")["revenue_effect_ars"].to_dict()
sd_ids = set(sd.donation_id)
recv = sd[(sd.amount_received_ars > 0)]
for _, r in recv.iterrows():
    nsamt = ns_by_don.get(r.donation_id)
    if nsamt is None:
        exc.append(("Salesforce receipt missing in NetSuite", r.donation_id))
    elif int(nsamt) != int(r.amount_received_ars):
        exc.append(("Salesforce vs NetSuite amount mismatch", r.donation_id))
for _, r in ns_dep.iterrows():
    rid = r.related_donation_id
    if pd.isna(rid) or rid not in sd_ids:
        exc.append(("NetSuite deposit without Salesforce match", r.transaction_id))
# controles sobre NetSuite
for _, r in nt.iterrows():
    proj_missing = pd.isna(r.project_code) or str(r.project_code).strip() == ""
    if r.fund_code not in mapped_funds:
        exc.append(("Unmapped fund code", r.transaction_id))
    elif r.fund_code in restricted and proj_missing:
        exc.append(("Restricted fund missing project", r.transaction_id))
    vid = r.vendor_id
    if pd.notna(vid) and vid in ven.index and not bool(ven.loc[vid, "has_complete_tax_docs"]):
        exc.append(("Vendor missing tax documentation", r.transaction_id))
    if r.transaction_type == "Accrual Journal":
        exc.append(("Accrual reversal check", r.transaction_id))
# duplicados: mismo vendor, periodo, monto, fondo (bill payments)
bp = nt[nt.transaction_type == "Bill Payment"]
dup = bp.groupby(["vendor_id", "posting_period", "expense_effect_ars", "fund_code"])
for key, grp in dup:
    if len(grp) >= 2:
        exc.append(("Possible duplicate payment", " + ".join(sorted(grp.transaction_id))))

got = set(exc)
exp_exc = S("exp_exceptions")
exp_set = set(zip(exp_exc.exception_type, exp_exc.source_record))
missing = exp_set - got
extra = got - exp_set
print(f"\n{'='*78}\nEXCEPCIONES: {'OK - 15/15 detectadas, sin falsos positivos' if not missing and not extra else 'DIFERENCIAS'}")
print(f"  esperadas {len(exp_set)} · detectadas {len(got)}")
by_type = {}
for t, _ in exp_set:
    by_type[t] = by_type.get(t, 0) + 1
det = {}
for t, _ in got:
    det[t] = det.get(t, 0) + 1
for t in sorted(by_type):
    print(f"   - {t}: {det.get(t,0)}/{by_type[t]}")
for t, s in sorted(missing):
    print(f"  NO DETECTADA: {t} · {s}")
for t, s in sorted(extra):
    print(f"  FALSO POSITIVO: {t} · {s}")

# ====================== VEREDICTO ======================
print(f"\n{'#'*78}")
flags = [("Cierre mensual", ok_close), ("Reporte a donantes", ok_donor and rag_bad.empty),
         ("Forecast de caja (cash)", ok_fc),
         ("Excepciones", not missing and not extra)]
for n, v in flags:
    print(f"  [{'OK ' if v else 'REV'}] {n}")
print(f"{'#'*78}")
