"""K7 · Salidas, KPI (ISO 22400-2, EN 15341), validación estadística y valoración económica."""
import math
import numpy as np
import pandas as pd
from scipy import stats

META_OEE = 0.85


# ---------------------------------------------------------------- KPI de una corrida
def kpi_desde_registros(eventos, lotes, lineas, preventivos=None, alertas=None,
                        horas_tecnico=None):
    """Calcula los KPI desde un registro de eventos y de lotes. Sirve igual para la
    salida del simulador y para los registros reales de la planta (módulo analítico)."""
    ev = pd.DataFrame(eventos)
    lt = pd.DataFrame(lotes)
    ln = lineas.set_index("linea")
    if ev.empty:
        ev = pd.DataFrame(columns=["linea", "tipo", "inicio_parada_h", "fin_parada_h",
                                   "inicio_atencion_h", "espera_repuesto_h", "codigo_equipo"])
    ev = ev.copy()
    ev["duracion_h"] = ev["fin_parada_h"] - ev["inicio_parada_h"]
    no_planif = ev[ev["tipo"].isin(["falla_tecnica", "no_tecnica"])]
    fallas = ev[ev["tipo"] == "falla_tecnica"]

    filas = []
    for linea, r in ln.iterrows():
        marcha = float(lt.loc[lt["linea"] == linea, "marcha_h"].sum()) if not lt.empty else 0.0
        paradas = float(no_planif.loc[no_planif["linea"] == linea, "duracion_h"].sum())
        plan = marcha + paradas
        disp = marcha / plan if plan > 0 else 1.0
        oee = disp * r["rendimiento"] * r["calidad"]
        filas.append(dict(linea=linea, tiempo_planificado_h=plan, horas_marcha=marcha,
                          paradas_h=paradas, disponibilidad=disp, rendimiento=r["rendimiento"],
                          calidad=r["calidad"], oee=oee,
                          techo_oee=r["rendimiento"] * r["calidad"],
                          fallas=int((fallas["linea"] == linea).sum())))
    por_linea = pd.DataFrame(filas)

    marcha_tot = por_linea["horas_marcha"].sum()
    plan_tot = por_linea["tiempo_planificado_h"].sum()
    n_f = len(fallas)
    resp = fallas["inicio_atencion_h"] - fallas["inicio_parada_h"]
    espera = fallas["espera_repuesto_h"]
    dur = fallas["duracion_h"]
    rep = dur - resp - espera
    planta = dict(
        oee=float((por_linea["oee"] * por_linea["tiempo_planificado_h"]).sum() / plan_tot),
        disponibilidad=float(marcha_tot / plan_tot),
        mtbf_h=float(marcha_tot / n_f) if n_f else math.inf,
        mttr_h=float(dur.mean()) if n_f else 0.0,
        mttr_respuesta_h=float(resp.mean()) if n_f else 0.0,
        mttr_espera_h=float(espera.mean()) if n_f else 0.0,
        mttr_reparacion_h=float(rep.mean()) if n_f else 0.0,
        respuesta_mediana_min=float(resp.median() * 60) if n_f else 0.0,
        fallas=n_f,
        paradas_no_planificadas_h=float(no_planif["duracion_h"].sum()),
        paradas_tecnicas_h=float(dur.sum()),
        esperas_repuesto=int((espera > 0).sum()),
        horas_marcha=float(marcha_tot),
        tiempo_planificado_h=float(plan_tot),
    )
    if not lt.empty and "fin_h" in lt:
        lt = lt.dropna(subset=["fin_h"])
        lead = lt["fin_h"] - lt["llegada_h"]
        planta["lead_time_medio_h"] = float(lead.mean())
        planta["lotes_terminados"] = int(len(lt))
        planta["lotes_con_parada"] = int((lt["paradas_h"] > 0).sum())
        planta["lotes_retrasados"] = int(((lead - lt["marcha_std_h"]) > 8.0).sum())
    if preventivos is not None:
        pv = pd.DataFrame(preventivos)
        planta["cumplimiento_preventivo"] = float(pv["ejecutado"].mean()) if len(pv) else 0.0
        planta["preventivos_ejecutados"] = int(pv["ejecutado"].sum()) if len(pv) else 0
    if alertas is not None:
        al = pd.DataFrame(alertas)
        for t in ("anticipada", "tardía", "falsa"):
            planta[f"alertas_{t}"] = int((al["tipo"] == t).sum()) if len(al) else 0
    if horas_tecnico is not None:
        planta["horas_tecnico"] = float(horas_tecnico)
    planta["ot_programadas"] = int((ev["tipo"] == "ot_programada").sum())
    return planta, por_linea


def kpi_simulacion(sim):
    return kpi_desde_registros(sim.eventos, sim.lotes, sim.p["lineas"], sim.preventivos,
                               sim.alertas, sim.horas_tecnico)


def techo_planta(lineas):
    """Techo de OEE de planta (disponibilidad = 100 %) con los pesos de la línea base."""
    w = lineas["tiempo_planificado_h"]
    return float((lineas["rendimiento"] * lineas["calidad"] * w).sum() / w.sum())


def brecha_cerrada(oee_esc, oee_asis, techo):
    return (oee_esc - oee_asis) / (techo - oee_asis) if techo > oee_asis else 0.0


# ---------------------------------------------------------------- estadística
def intervalo_confianza(x, nivel=0.95):
    x = np.asarray(x, dtype=float)
    n = len(x)
    m = float(x.mean())
    if n < 2:
        return m, 0.0
    h = float(stats.t.ppf(0.5 + nivel / 2, n - 1) * x.std(ddof=1) / math.sqrt(n))
    return m, h


def replicas_necesarias(x, semiancho_objetivo, nivel=0.95):
    x = np.asarray(x, dtype=float)
    s = x.std(ddof=1)
    z = stats.norm.ppf(0.5 + nivel / 2)
    return int(math.ceil((z * s / semiancho_objetivo) ** 2))


def anova_factorial(df, respuesta="oee"):
    """ANOVA del diseño factorial 2^k con bloques por réplica (números aleatorios comunes).
    df: columnas A, B (0/1), replica y la respuesta. R2 v2: diseño 2² (TPM × IoT)."""
    d = df.copy()
    factores = [f for f in "AB" if f in d.columns]
    for f in factores:
        d[f] = d[f].astype(int) * 2 - 1
    y = d[respuesta].to_numpy(float)
    n_rep = d["replica"].nunique()
    N = len(d)
    n_celdas = 2 ** len(factores)
    efectos = {"A (TPM)": d.A, "B (IoT)": d.B, "A×B (TPM × IoT)": d.A * d.B}
    filas = []
    ss_modelo = 0.0
    for nombre, col in efectos.items():
        contraste = float((y * col).sum())
        ss = contraste ** 2 / N
        efecto = 2 * contraste / N
        ss_modelo += ss
        filas.append([nombre, efecto, ss, 1])
    medias_bloque = d.groupby("replica")[respuesta].mean()
    ss_bloque = float(n_celdas * ((medias_bloque - y.mean()) ** 2).sum())
    ss_total = float(((y - y.mean()) ** 2).sum())
    ss_error = ss_total - ss_modelo - ss_bloque
    gl_error = (n_celdas - 1) * (n_rep - 1)
    cm_error = ss_error / gl_error if gl_error > 0 else float("nan")
    tabla = pd.DataFrame(filas, columns=["Fuente", "Efecto", "SC", "gl"])
    tabla["CM"] = tabla["SC"] / tabla["gl"]
    tabla["F"] = tabla["CM"] / cm_error
    tabla["p"] = stats.f.sf(tabla["F"], 1, gl_error)
    extra = pd.DataFrame([["Bloques (réplicas)", np.nan, ss_bloque, n_rep - 1,
                           ss_bloque / max(1, n_rep - 1), np.nan, np.nan],
                          ["Error", np.nan, ss_error, gl_error, cm_error, np.nan, np.nan],
                          ["Total", np.nan, ss_total, N - 1, np.nan, np.nan, np.nan]],
                         columns=tabla.columns)
    return pd.concat([tabla, extra], ignore_index=True)


# ---------------------------------------------------------------- valoración económica
def valoracion_economica(k_esc, k_asis, escenario, eco, n_sensores, n_clase_a):
    """Costos anuales del escenario frente al AS-IS (misma réplica)."""
    def costo_operacion(k):
        return (k.get("horas_tecnico", 0) * eco["costo_hora_tecnico"]
                + k["esperas_repuesto"] * eco["costo_compra_urgente"]
                + k["paradas_no_planificadas_h"] * eco["costo_hora_parada"]
                + k.get("lotes_retrasados", 0) * eco["costo_lote_retrasado"])

    inversion, recurrente = 0.0, 0.0
    if escenario.tpm:
        inversion += eco["costo_capacitacion_tpm"]
        recurrente += (eco["inspeccion_autonoma_min_dia"] / 60 * n_clase_a
                       * eco["dias_operacion"] * eco["costo_hora_operador"])
        prev_extra = max(0, k_esc.get("preventivos_ejecutados", 0)
                         - k_asis.get("preventivos_ejecutados", 0))
        recurrente += prev_extra * eco["costo_materiales_preventivo"]
    if escenario.iot:
        inversion += n_sensores * eco["costo_sensor_equipo"] + eco["costo_pasarela"]
        recurrente += 12 * eco["costo_plataforma_mes"]
    ahorro = costo_operacion(k_asis) - costo_operacion(k_esc)
    neto = ahorro - recurrente
    payback = inversion / (neto / 12) if neto > 0 and inversion > 0 else (0.0 if inversion == 0 else math.inf)
    disponible = eco["presupuesto_mto_no_ejecutado"] + eco["presupuesto_rep_no_ejecutado"]
    return dict(inversion_inicial=inversion, costo_recurrente=recurrente,
                ahorro_operativo=ahorro, beneficio_neto_anual=neto,
                periodo_recuperacion_meses=payback,
                financiable=(inversion + recurrente) <= disponible,
                presupuesto_disponible=disponible)
