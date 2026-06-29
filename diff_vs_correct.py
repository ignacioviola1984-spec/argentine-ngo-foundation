"""
diff_vs_correct.py  -  Cruza el output calculado contra los resultados correctos
(exp_*) celda por celda y muestra EXACTAMENTE donde falla, sin redondear la verdad.
"""
import os
import sys
import numpy as np
import pandas as pd

PATH = (sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("POTENCIAR_DATASET", "potenciar_synthetic_dataset.xlsx"))
if not os.path.exists(PATH):
    sys.exit(f"Dataset no encontrado: {PATH}\n"
             f"Uso: python diff_vs_correct.py <ruta_al_xlsx>  (o POTENCIAR_DATASET=<ruta>)")
ASOF = pd.Timestamp("2026-06-30"); OPENING = 13167000
BURN_MONTHS = ["2026-04", "2026-05", "2026-06"]
xl = pd.ExcelFile(PATH); S = lambda n: xl.parse(n)
fund_map = S("fund_project_map"); mapped = set(fund_map.fund_code)
restricted = set(fund_map.loc[fund_map.restriction_type == "Restricted", "fund_code"])
nt = S("ns_transactions"); sd = S("sf_donations"); bud = S("budget_plan")
fr = S("forecast_receipts"); fp = S("forecast_payments"); ven = S("ns_vendors").set_index("vendor_id")
for df, c in [(sd, "pledge_date"), (sd, "expected_receipt_date"), (sd, "received_date"),
              (fr, "expected_date"), (fp, "expected_payment_date")]:
    df[c] = pd.to_datetime(df[c], errors="coerce")


def cell_diff(name, comp, exp, keys, cols, pct=()):
    comp = comp.sort_values(keys).reset_index(drop=True); exp = exp.sort_values(keys).reset_index(drop=True)
    m = exp.merge(comp, on=keys, how="outer", suffixes=("_exp", "_got"), indicator=True)
    fails = []
    for _, r in m[m._merge != "both"].iterrows():
        fails.append((tuple(r[k] for k in keys), "FILA", r._merge))
    both = m[m._merge == "both"]; cells = len(both) * (len(cols) + len(pct))
    for col in cols:
        bad = both[(both[f"{col}_got"].fillna(0) - both[f"{col}_exp"].fillna(0)).abs() > 0.5]
        for _, r in bad.iterrows():
            fails.append((tuple(r[k] for k in keys), col, f"correcto {r[f'{col}_exp']} vs mio {r[f'{col}_got']}"))
    for col in pct:
        bad = both[(both[f"{col}_got"].round(4).fillna(-9) - both[f"{col}_exp"].round(4).fillna(-9)).abs() > 5e-4]
        for _, r in bad.iterrows():
            fails.append((tuple(r[k] for k in keys), col, f"correcto {r[f'{col}_exp']} vs mio {r[f'{col}_got']}"))
    print(f"\n{'='*80}\n{name}: {len(both)*(len(cols)+len(pct))} celdas comparadas · "
          f"{'TODAS OK' if not fails else str(len(fails)) + ' FALLAS'}")
    for k, c, d in fails:
        print(f"   FALLA {k} · {c}: {d}")
    return not fails


# ---- close ----
g = nt.groupby(["posting_period", "fund_code"])
close = pd.DataFrame({
    "cash_receipts_ars": g.apply(lambda x: x.loc[x.cash_effect_ars > 0, "cash_effect_ars"].sum()),
    "cash_payments_ars": g.apply(lambda x: -x.loc[x.cash_effect_ars < 0, "cash_effect_ars"].sum()),
    "revenue_ars": g.revenue_effect_ars.sum(), "expenses_ars": g.expense_effect_ars.sum(),
}).reset_index().rename(columns={"posting_period": "period"})
close["net_cash_flow_ars"] = close.cash_receipts_ars - close.cash_payments_ars
budg = bud.groupby(["period", "fund_code"]).budget_amount_ars.sum().reset_index().rename(
    columns={"budget_amount_ars": "budget_expenses_ars"})
close = close.merge(budg, on=["period", "fund_code"], how="left")
close["budget_expenses_ars"] = close.budget_expenses_ars.fillna(0).astype(int)
close["expense_variance_vs_budget_ars"] = close.budget_expenses_ars - close.expenses_ars
close["expense_variance_pct"] = np.where(close.budget_expenses_ars != 0,
    (close.expenses_ars - close.budget_expenses_ars) / close.budget_expenses_ars, np.nan)
close["status"] = np.where(close.fund_code.isin(mapped), "OK", "Review")
ok_close = cell_diff("CIERRE MENSUAL", close, S("exp_close_summary"), ["period", "fund_code"],
    ["cash_receipts_ars", "cash_payments_ars", "net_cash_flow_ars", "revenue_ars", "expenses_ars",
     "budget_expenses_ars", "expense_variance_vs_budget_ars"], pct=["expense_variance_pct"])
sc = close.merge(S("exp_close_summary")[["period", "fund_code", "status"]], on=["period", "fund_code"],
                 suffixes=("_got", "_exp"))
print("   status cierre:", "OK" if (sc.status_got == sc.status_exp).all() else
      list(sc[sc.status_got != sc.status_exp][["period", "fund_code"]].itertuples(index=False)))

# ---- donor ----
received = nt.groupby("fund_code").revenue_effect_ars.sum(); spend = nt.groupby("fund_code").expense_effect_ars.sum()
pl = sd[(sd.expected_receipt_date <= ASOF) | (sd.amount_received_ars > 0)].groupby("fund_code").amount_pledged_ars.sum()
burn3 = nt[nt.posting_period.isin(BURN_MONTHS)].groupby("fund_code").expense_effect_ars.sum() / 3.0
donor = pd.DataFrame([{
    "fund_code": f.fund_code, "pledged_through_asof_ars": int(pl.get(f.fund_code, 0)),
    "received_through_asof_ars": int(received.get(f.fund_code, 0)), "spend_through_asof_ars": int(spend.get(f.fund_code, 0)),
    "remaining_fund_balance_ars": int(received.get(f.fund_code, 0) - spend.get(f.fund_code, 0)),
    "avg_monthly_burn_last_3_months_ars": int(round(burn3.get(f.fund_code, 0))),
} for _, f in fund_map.iterrows()])
ok_donor = cell_diff("REPORTE A DONANTES", donor, S("exp_donor_report"), ["fund_code"],
    ["pledged_through_asof_ars", "received_through_asof_ars", "spend_through_asof_ars",
     "remaining_fund_balance_ars", "avg_monthly_burn_last_3_months_ars"])

# ---- forecast: cash exacto, y runway con dos bases de burn ----
exp_fc = S("exp_cash_forecast"); exp_fc["week_start"] = pd.to_datetime(exp_fc.week_start); exp_fc["week_end"] = pd.to_datetime(exp_fc.week_end)
weeks = list(zip(exp_fc.week_start, exp_fc.week_end))
rows, cash = [], OPENING
for ws, we in weeks:
    r = int(fr.loc[(fr.expected_date >= ws) & (fr.expected_date <= we), "probability_weighted_amount_ars"].sum())
    p = int(fp.loc[(fp.expected_payment_date >= ws) & (fp.expected_payment_date <= we), "expected_amount_ars"].sum())
    rows.append({"week_start": ws, "opening_cash_ars": cash, "expected_receipts_ars": r,
                 "expected_payments_ars": p, "closing_cash_ars": cash + r - p}); cash += r - p
fcst = pd.DataFrame(rows)
ok_cash = cell_diff("FORECAST DE CAJA (cash)", fcst, exp_fc, ["week_start"],
    ["opening_cash_ars", "expected_receipts_ars", "expected_payments_ars", "closing_cash_ars"])

burn_expense = donor.avg_monthly_burn_last_3_months_ars.sum() * 12.0 / 52.0   # lo que use antes (incluye accrual)
burn_cash = close[close.period.isin(BURN_MONTHS)].cash_payments_ars.sum() / 13.0  # burn de CAJA (sin accrual)
fm = fcst.merge(exp_fc[["week_start", "closing_cash_ars", "runway_weeks", "status"]].rename(
    columns={"closing_cash_ars": "cc"}), on="week_start")
fm["rw_correcto"] = fm.runway_weeks
fm["rw_mio_gasto"] = (fm.closing_cash_ars / burn_expense).round(1)
fm["rw_cash"] = (fm.closing_cash_ars / burn_cash).round(1)
rag = lambda s: np.where(s >= 8, "Green", np.where(s >= 3, "Amber", "Red"))
fm["rag_correcto"] = fm.status; fm["rag_mio_gasto"] = rag(fm.rw_mio_gasto); fm["rag_cash"] = rag(fm.rw_cash)
print(f"\n{'='*80}\nRUNWAY_WEEKS  (burn gasto={burn_expense:,.0f}  ·  burn caja={burn_cash:,.0f} ARS/sem)")
print(f"{'semana':12}{'cierre':>12}{'correcto':>10}{'mio(gasto)':>12}{'caja':>8}   RAG corr/mio/caja")
for _, r in fm.iterrows():
    flag = "  <-- FALLE" if r.rw_mio_gasto != r.rw_correcto else ""
    print(f"{str(r.week_start.date()):12}{int(r.closing_cash_ars):>12,}{r.rw_correcto:>10}"
          f"{r.rw_mio_gasto:>12}{r.rw_cash:>8}   {r.rag_correcto}/{r.rag_mio_gasto}/{r.rag_cash}{flag}")
miss_rw_gasto = int((fm.rw_mio_gasto != fm.rw_correcto).sum()); miss_rw_cash = int((fm.rw_cash != fm.rw_correcto).sum())
miss_rag_gasto = int((fm.rag_mio_gasto != fm.rag_correcto).sum()); miss_rag_cash = int((fm.rag_cash != fm.rag_correcto).sum())
print(f"  runway mio(gasto): {miss_rw_gasto}/13 mal · con burn de CAJA: {miss_rw_cash}/13 mal")
print(f"  RAG    mio(gasto): {miss_rag_gasto}/13 mal · con burn de CAJA: {miss_rag_cash}/13 mal")

# ---- exceptions ----
exc = set()
for _, r in sd.iterrows():
    if r.payment_status == "Overdue" or (pd.notna(r.expected_receipt_date) and r.expected_receipt_date <= ASOF and r.amount_received_ars == 0):
        exc.add(("Overdue pledged receipt", r.donation_id))
ns_dep = nt[nt.revenue_effect_ars > 0]; ns_by_don = ns_dep.set_index("related_donation_id")["revenue_effect_ars"].to_dict(); sd_ids = set(sd.donation_id)
for _, r in sd[sd.amount_received_ars > 0].iterrows():
    a = ns_by_don.get(r.donation_id)
    if a is None: exc.add(("Salesforce receipt missing in NetSuite", r.donation_id))
    elif int(a) != int(r.amount_received_ars): exc.add(("Salesforce vs NetSuite amount mismatch", r.donation_id))
for _, r in ns_dep.iterrows():
    if pd.isna(r.related_donation_id) or r.related_donation_id not in sd_ids:
        exc.add(("NetSuite deposit without Salesforce match", r.transaction_id))
for _, r in nt.iterrows():
    pm = pd.isna(r.project_code) or str(r.project_code).strip() == ""
    if r.fund_code not in mapped: exc.add(("Unmapped fund code", r.transaction_id))
    elif r.fund_code in restricted and pm: exc.add(("Restricted fund missing project", r.transaction_id))
    if pd.notna(r.vendor_id) and r.vendor_id in ven.index and not bool(ven.loc[r.vendor_id, "has_complete_tax_docs"]):
        exc.add(("Vendor missing tax documentation", r.transaction_id))
    if r.transaction_type == "Accrual Journal": exc.add(("Accrual reversal check", r.transaction_id))
for key, grp in nt[nt.transaction_type == "Bill Payment"].groupby(["vendor_id", "posting_period", "expense_effect_ars", "fund_code"]):
    if len(grp) >= 2: exc.add(("Possible duplicate payment", " + ".join(sorted(grp.transaction_id))))
exp_set = set(zip(S("exp_exceptions").exception_type, S("exp_exceptions").source_record))
miss, extra = exp_set - exc, exc - exp_set
print(f"\n{'='*80}\nEXCEPCIONES: {len(exc)} detectadas vs {len(exp_set)} correctas · "
      f"{'TODAS OK' if not miss and not extra else 'FALLAS'}")
for t, s in sorted(miss): print(f"   NO DETECTADA: {t} · {s}")
for t, s in sorted(extra): print(f"   FALSO POSITIVO: {t} · {s}")

print(f"\n{'#'*80}\nDONDE FALLE (vs resultados correctos)\n{'#'*80}")
print(f"  Cierre mensual ........ {'OK 100%' if ok_close else 'FALLAS'}")
print(f"  Reporte a donantes .... {'OK 100%' if ok_donor else 'FALLAS'}")
print(f"  Forecast caja (cash) .. {'OK 100%' if ok_cash else 'FALLAS'}")
print(f"  Excepciones ........... {'OK 15/15' if not miss and not extra else 'FALLAS'}")
print(f"  runway_weeks .......... FALLE {miss_rw_gasto}/13 (use burn de gasto, no de caja); con burn de caja {miss_rw_cash}/13")
print(f"  RAG forecast .......... FALLE {miss_rag_gasto}/13; con burn de caja {miss_rag_cash}/13")
