"""Comparación de escenarios y recomendación para la vista de decisión."""
import math
import pandas as pd

from .escenarios import CODIGO_ASIS

from .kpi import intervalo_confianza


def tabla_comparacion(df):
    filas = []
    for esc, g in df.groupby("escenario", sort=False):
        oee, oee_h = intervalo_confianza(g["oee"])
        disp, disp_h = intervalo_confianza(g["disponibilidad"])
        neto = float(g["beneficio_neto_anual"].mean())
        inv = float(g["inversion_inicial"].mean())
        payback = 0.0 if inv == 0 else (inv / (neto / 12) if neto > 0 else math.inf)
        filas.append({
            "Escenario": esc, "Código": g["codigo"].iloc[0],
            "OEE (%)": 100 * oee, "± IC 95 %": 100 * oee_h,
            "Disponibilidad (%)": 100 * disp,
            "MTBF (h)": g["mtbf_h"].mean(), "MTTR (h)": g["mttr_h"].mean(),
            "Paradas no planificadas (h/año)": g["paradas_no_planificadas_h"].mean(),
            "Brecha atribuible cerrada (%)": 100 * g["brecha_cerrada"].mean(),
            "Inversión inicial (S/)": inv,
            "Costo recurrente (S/ año)": g["costo_recurrente"].mean(),
            "Ahorro operativo (S/ año)": g["ahorro_operativo"].mean(),
            "Beneficio neto (S/ año)": neto,
            "Recuperación (meses)": payback,
            "Financiable con presupuesto no ejecutado": bool(g["financiable"].iloc[0]),
        })
    return pd.DataFrame(filas)


def recomendar(tabla, meses_max=12):
    """Elige el escenario con mayor OEE entre los financiables que se recuperan en
    el plazo indicado; si ninguno cumple, el de mayor beneficio neto."""
    cand = tabla[(tabla["Código"] != CODIGO_ASIS) & tabla["Financiable con presupuesto no ejecutado"]
                 & (tabla["Recuperación (meses)"] <= meses_max)]
    if cand.empty:
        mejor = tabla.sort_values("Beneficio neto (S/ año)", ascending=False).iloc[0]
        motivo = "ningún escenario se recupera en el plazo; se elige el de mayor beneficio neto"
    else:
        mejor = cand.sort_values("OEE (%)", ascending=False).iloc[0]
        motivo = (f"mayor OEE entre los escenarios financiables que se recuperan en "
                  f"{meses_max} meses o menos")
    rapido = tabla[tabla["Código"] != CODIGO_ASIS].sort_values("Recuperación (meses)").iloc[0]
    return mejor, rapido, motivo
