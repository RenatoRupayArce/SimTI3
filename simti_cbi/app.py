"""K8 · SimTI-CBI — R2 TPM + IoT · Aplicación interactiva (Streamlit).

Ejecutar:  streamlit run app.py

Dos bloques:
- Planta (datos registrados): IoT · Monitoreo, TPM · Gestión del mantenimiento, ficha de máquina
  e indicadores, a partir del libro Excel de registros (de CBI o el ejemplo sintético).
- Modelo (simulación para decidir): situación actual, simulador, comparación y validación,
  a partir de los parámetros del diagnóstico (carpeta datos/).
La aplicación no se conecta a sensores físicos: muestra lo que se registra en el Excel.
"""
import copy
import dataclasses
import html
import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from simti.datos import cargar_parametros, niveles_escenario, CARPETA_DATOS
from simti.ajuste import calibrar, ajustar_weibull
from simti.escenarios import Escenario, diseno_factorial, CODIGO_ASIS
from simti.kpi import (kpi_desde_registros, techo_planta, anova_factorial, intervalo_confianza, META_OEE)
from simti.experimento import correr, correr_sensibilidad
from simti.decision import tabla_comparacion, recomendar
from simti.registros import leer_excel, kpi_por_equipo, resumen_tpm, estado_sensores, libro_actualizado

st.set_page_config(page_title="SimTI-CBI · R2 TPM + IoT", page_icon="⚙️", layout="wide")
print("SimTI: inicio del script", flush=True)

C = dict(iot="#0E7490", tpm="#4338CA", ok="#15803D", warn="#B45309", bad="#B91C1C",
         gris="#64748B", tinta="#0F172A", borde="#E2E8F0", claro="#CBD5E1")
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": C["claro"], "axes.labelcolor": C["tinta"],
                     "xtick.color": C["gris"], "ytick.color": C["gris"], "axes.titleweight": "bold",
                     "axes.titlesize": 10.5, "axes.titlelocation": "left"})

st.markdown("""
<style>
:root{--iot:#0E7490;--tpm:#4338CA;--ok:#15803D;--warn:#B45309;--bad:#B91C1C;--gris:#64748B;
      --tinta:#0F172A;--borde:#E2E8F0}
.block-container{padding-top:1.4rem;max-width:1320px}
.cbi-banner{border-radius:10px;padding:9px 14px;font-size:.9rem;margin:.1rem 0 1rem;border:1px solid}
.cbi-banner.sint{background:#FFFBEB;border-color:#FCD34D;color:#78350F}
.cbi-banner.real{background:#F0FDF4;border-color:#86EFAC;color:#14532D}
.cbi-banner.info{background:#F0F9FF;border-color:#BAE6FD;color:#0C4A6E}
.cbi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin:.3rem 0 1rem}
.cbi-card{background:#fff;border:1px solid var(--borde);border-radius:12px;padding:14px 16px}
.cbi-card.iot{border-top:3px solid var(--iot)} .cbi-card.tpm{border-top:3px solid var(--tpm)}
.cbi-card h4{margin:0 0 2px 0;font-size:1rem;color:var(--tinta);display:flex;align-items:center;gap:8px}
.cbi-card .sub{color:var(--gris);font-size:.8rem;margin-bottom:8px}
.cbi-badge{display:inline-flex;align-items:center;gap:5px;font-size:.74rem;font-weight:600;
           padding:2px 9px;border-radius:999px;white-space:nowrap}
.b-ok{background:#DCFCE7;color:#166534}.b-warn{background:#FEF3C7;color:#92400E}
.b-bad{background:#FEE2E2;color:#991B1B}.b-gris{background:#F1F5F9;color:#475569}
.b-iot{background:#CFFAFE;color:#155E75}.b-tpm{background:#E0E7FF;color:#3730A3}
.cbi-row{display:flex;justify-content:space-between;align-items:center;font-size:.84rem;padding:5px 0;
         border-top:1px dashed var(--borde);gap:8px}
.cbi-row .v{font-variant-numeric:tabular-nums;color:var(--tinta);font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;flex:none}
.cbi-foot{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:.78rem;color:var(--gris);margin-top:8px}
.cbi-flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:.4rem 0 1.2rem}
.cbi-step{flex:1 1 160px;border-radius:12px;padding:12px 14px;color:#fff}
.cbi-step b{display:block;font-size:.93rem;margin-bottom:4px}.cbi-step span{font-size:.8rem;opacity:.95}
.cbi-arrow{align-self:center;color:var(--gris);font-size:1.2rem}
.cbi-veredicto{border-radius:12px;padding:14px 16px;border:1px solid var(--borde);margin-bottom:.6rem}
.cbi-veredicto .t{font-size:.8rem;color:var(--gris);text-transform:uppercase;letter-spacing:.04em}
.cbi-veredicto .r{font-size:1.25rem;font-weight:700;margin:4px 0 6px}
.cbi-veredicto p{font-size:.88rem;margin:0 0 4px 0;color:var(--tinta)}
.cbi-tip{position:relative;display:inline-flex;align-items:center;justify-content:center;width:17px;
         height:17px;border-radius:50%;border:1px solid #94A3B8;color:#475569;font-size:11px;font-weight:700;
         cursor:help;background:#fff;flex:none}
.cbi-tip .cbi-tiptext{visibility:hidden;opacity:0;position:absolute;z-index:50;bottom:140%;left:-10px;
         width:min(260px,80vw);background:#0F172A;color:#F8FAFC;font-weight:400;font-size:12.5px;
         line-height:1.4;padding:8px 10px;border-radius:8px;text-align:left;transition:opacity .15s;
         text-transform:none;letter-spacing:0}
.cbi-tip:hover .cbi-tiptext,.cbi-tip:focus .cbi-tiptext{visibility:visible;opacity:1}
.cbi-tip:focus{outline:2px solid var(--iot);outline-offset:2px}
@media (max-width:640px){.cbi-arrow{display:none}.cbi-step{flex-basis:100%}}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ textos de ayuda contextual
AYUDA = {
    "iot": "Muestra la información que los sensores instalados en las máquinas registran (vibración, "
           "temperatura y corriente) y las alertas que generan. Sirve para detectar condiciones anormales "
           "antes de que el equipo falle.",
    "tpm": "Gestiona las actividades de mantenimiento: plan preventivo, órdenes originadas por alertas IoT "
           "y su cumplimiento. Su objetivo es mejorar la disponibilidad y la confiabilidad de los equipos.",
    "ficha": "Reúne en una sola pantalla lo que IoT detecta en una máquina y lo que TPM hace con ella: "
             "sensores, alertas, órdenes de trabajo, fallas e indicadores.",
    "transmision": "Indica si el sensor tiene lecturas recientes en el registro (hasta 24 h antes de la fecha "
                   "de corte). Se infiere de los datos cargados: la aplicación no tiene un enlace en tiempo real.",
    "condicion": "Compara la última lectura con el límite de alerta del sensor. «Fuera de límite» indica una "
                 "condición anormal que debería generar una revisión o una orden de trabajo.",
    "fuera_limite": "Número de lecturas del periodo que superaron el límite de alerta de su sensor.",
    "alertas": "Avisos de la plataforma IoT. Anticipada: llegó a tiempo y se programó una OT sin parar el equipo. "
               "Tardía: la falla ocurrió, pero el técnico llegó antes. Falsa: se revisó y no había falla.",
    "cumplimiento": "Órdenes realizadas ÷ órdenes que ya debían estar hechas a la fecha de corte "
                    "(realizadas + vencidas). Las pendientes aún no vencen y no se cuentan.",
    "vencidas": "Órdenes cuya fecha programada ya pasó y no tienen fecha de ejecución.",
    "pendientes": "Órdenes programadas para después de la fecha de corte: trabajo por hacer.",
    "ot_iot": "Órdenes de trabajo creadas a partir de una alerta IoT anticipada. Es el punto donde IoT y TPM "
              "se conectan: el sensor detecta y TPM programa la intervención.",
    "oee": "Eficiencia global de los equipos = disponibilidad × rendimiento × calidad (ISO 22400-2). "
           "Es el indicador principal de la solución.",
    "disponibilidad": "Horas en marcha ÷ (horas en marcha + horas de parada no planificada).",
    "mtbf": "Tiempo medio entre fallas: horas de marcha ÷ número de fallas técnicas. Más alto es mejor.",
    "mttr": "Tiempo medio por falla: respuesta del técnico + espera de repuesto + reparación. Más bajo es mejor.",
    "paradas": "Horas al año en que los equipos estuvieron detenidos sin que estuviera planificado.",
    "brecha": "Parte de la distancia entre el OEE actual y el techo alcanzable (80,3 %, disponibilidad del "
              "100 %) que se logra cerrar. Rendimiento y calidad no cambian en el modelo.",
    "tpm_check": "Activa las prácticas TPM en los 6 equipos clase A: plan preventivo con el cumplimiento elegido, "
                 "mantenimiento autónomo (checklist diario de 15 min) y reparación estandarizada.",
    "cumpl_slider": "Porcentaje de las órdenes preventivas del plan que realmente se ejecutan en los 6 equipos "
                    "clase A (12 órdenes por equipo al año). Hoy CBI cumple el 38,6 %. Con más cumplimiento, "
                    "los equipos fallan menos por desgaste, pero cada orden cuesta horas de técnico y materiales.",
    "iot_check": "Instala sensores de vibración, temperatura y corriente en los equipos elegidos. Una alerta "
                 "anticipada permite programar la reparación sin detener el lote.",
    "sensores": "Equipos donde se instalan sensores. Por defecto, los 5 equipos críticos con más fallas.",
    "tecnicos": "Personas de mantenimiento disponibles en el turno. Hoy hay 1. El AS-IS de comparación "
                "siempre usa 1.",
    "comprobacion": "Contrasta el escenario con la situación actual usando las mismas réplicas (mismas fallas y "
                    "lotes). La mejora del OEE se prueba con una prueba t pareada; el beneficio, con los costos "
                    "de la barra lateral.",
    "fuente": "De dónde salen los datos de las secciones IoT, TPM e indicadores. El simulador usa siempre los "
              "parámetros del diagnóstico.",
}
NOMBRES_PARAM = {
    "delta_tpm_mtbf": "Mejora del MTBF por TPM (δ_TPM)",
    "red_reparacion_tpm": "Reducción de la reparación por estandarización",
    "p_deteccion": "Probabilidad de detección IoT",
    "frac_anticipada": "Proporción de alertas anticipadas",
    "red_respuesta_alerta": "Reducción de la respuesta con alerta",
    "falsas_alarmas_mes": "Falsas alarmas por equipo y mes",
    "n_tecnicos": "Número de técnicos",
}
AYUDA_PARAM = {
    "delta_tpm_mtbf": "Cuánto más aguantan los equipos clase A entre fallas por desgaste con el preventivo al 100 %. "
                      "0,25 = +25 %.",
    "red_reparacion_tpm": "Cuánto más rápida es la reparación gracias a procedimientos estándar. 0,30 = 30 % menos.",
    "p_deteccion": "De las fallas que dan señales previas, qué fracción detecta el sensor.",
    "frac_anticipada": "De las alertas, qué fracción llega a tiempo para programar la OT sin parar el equipo.",
    "red_respuesta_alerta": "Cuánto se acorta la llegada del técnico cuando la alerta reemplaza al aviso por correo.",
    "falsas_alarmas_mes": "Alarmas sin falla real por equipo con sensor y mes. Cada una ocupa 30 min del técnico.",
}

ICONO = {
    "sensor": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0E7490" stroke-width="2" '
              'stroke-linecap="round" aria-hidden="true"><path d="M5 12a7 7 0 0 1 14 0"/><path d="M8.5 12a3.5 3.5 0 0 1 7 0"/>'
              '<circle cx="12" cy="12" r="1.2" fill="#0E7490"/><path d="M12 13v7"/></svg>',
    "llave": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4338CA" stroke-width="2" '
             'stroke-linecap="round" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 '
             '5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/></svg>',
    "maquina": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" '
               'aria-hidden="true"><rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8V5h10v3"/>'
               '<circle cx="12" cy="14" r="2.5"/></svg>',
}


SENSORES_INFO = {
    "vibr": dict(titulo="Vibración (RMS)", unidad="mm/s", color=C["iot"],
                 mide="La velocidad de vibración del equipo mientras opera.",
                 donde="Carcasa de los rodamientos del motor y del eje (agitador del reactor, mezcladora, molino).",
                 detecta="Desbalance, desalineación, holguras, rodamientos desgastados, martillos o paletas dañadas.",
                 revisar="Rodamientos, alineación motor–eje, pernos de fijación y estado de martillos o paletas."),
    "temp": dict(titulo="Temperatura", unidad="°C", color=C["warn"],
                 mide="La temperatura superficial del rodamiento o del motor.",
                 donde="Carcasa del rodamiento y cuerpo del motor.",
                 detecta="Fricción por falta o degradación del lubricante, sobrecarga y rodamientos en mal estado.",
                 revisar="Nivel y estado del lubricante, ventilación del motor y carga del lote."),
    "corr": dict(titulo="Corriente del motor", unidad="A", color=C["tpm"],
                 mide="La corriente eléctrica que consume el motor.",
                 donde="Alimentación del motor en el tablero (transformador de corriente).",
                 detecta="Sobrecarga, atascamiento de material, rozamientos y fallas eléctricas del motor.",
                 revisar="Atascos de material, carga del equipo, conexiones y estado del motor."),
}


def info_variable(variable):
    v = str(variable).lower()
    for clave, info in SENSORES_INFO.items():
        if clave in v:
            return info
    return None


def tip(texto):
    """Icono «?» accesible (hover, clic, toque y teclado) para bloques HTML."""
    t = html.escape(texto)
    return (f'<span class="cbi-tip" tabindex="0" role="button" aria-label="Ayuda: {t}">?'
            f'<span class="cbi-tiptext" role="tooltip">{t}</span></span>')


def badge(texto, clase):
    return f'<span class="cbi-badge {clase}">{html.escape(texto)}</span>'


def banner(texto, clase="info"):
    st.markdown(f'<div class="cbi-banner {clase}">{texto}</div>', unsafe_allow_html=True)


def pct(x, d=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f} %"


def num(x, d=1, suf=""):
    return "—" if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else f"{x:,.{d}f}{suf}"


def soles(x):
    return f"−S/ {abs(x):,.0f}" if x < 0 else f"S/ {x:,.0f}"


def figura_barras_h(etiquetas, valores, titulo, xlabel, color="#2f6f9f"):
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(etiquetas) + 1.2))
    ax.barh(etiquetas, valores, color=color)
    for i, v in enumerate(valores):
        ax.text(v, i, f" {v:.1f}", va="center", fontsize=9)
    ax.set_title(titulo)
    ax.set_xlabel(xlabel)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------------ datos del modelo (caché)
@st.cache_resource(show_spinner="Calibrando el AS-IS con la línea base…")
def parametros_calibrados():
    p, historial = calibrar(cargar_parametros())
    return p, historial


def con_economicos(p, eco):
    q = copy.copy(p)
    q["economicos"] = dict(eco)
    return q


@st.cache_data(show_spinner=False)
def corrida_asis(eco_items, n_rep):
    p, _ = parametros_calibrados()
    p = con_economicos(p, dict(eco_items))
    niv = niveles_escenario(p)
    from simti.motor import simular
    from simti.kpi import kpi_simulacion
    kp, lineas = [], []
    for r in range(n_rep):
        sim = simular(p, Escenario("AS-IS", niveles=niv), 2026 + r)
        k, pl = kpi_simulacion(sim)
        kp.append(k)
        lineas.append(pl.assign(replica=r))
        if r == 0:
            ev0 = pd.DataFrame(sim.eventos)
    return pd.DataFrame(kp), pd.concat(lineas), ev0


@st.cache_data(show_spinner=False)
def corrida_factorial(niv_items, eco_items, n_rep, n_tec):
    p, _ = parametros_calibrados()
    p = con_economicos(p, dict(eco_items))
    return correr(p, diseno_factorial(dict(niv_items), n_tec), n_rep)


def factorial_con_aviso(niv_items, eco_items, n_rep, n_tec):
    # El aviso va fuera de la función en caché (evita CacheReplayClosureError).
    with st.spinner("Simulando las 4 combinaciones del diseño 2² (TPM × IoT)…"):
        return corrida_factorial(niv_items, eco_items, n_rep, n_tec)


@st.cache_data(show_spinner=False)
def corrida_sensibilidad(niv_items, eco_items, n_rep):
    p, _ = parametros_calibrados()
    p = con_economicos(p, dict(eco_items))
    return correr_sensibilidad(p, dict(niv_items), n_rep)


@st.cache_data(show_spinner="Leyendo el libro de registros…")
def leer_registros(contenido):
    return leer_excel(io.BytesIO(contenido), cargar_parametros()["equipos"])


# ------------------------------------------------------------------ comprobación R2
def comprobar(df_esc, df_asis, eco):
    """Compara un escenario con el AS-IS réplica a réplica (números aleatorios comunes)."""
    e = df_esc.sort_values("replica") if "replica" in df_esc else df_esc
    a = df_asis.reset_index(drop=True)
    n = min(len(e), len(a))
    e, a = e.iloc[:n].reset_index(drop=True), a.iloc[:n]
    d_oee = e["oee"].to_numpy() - a["oee"].to_numpy()
    m_oee, h_oee = intervalo_confianza(d_oee)
    p_val = float(stats.ttest_rel(e["oee"], a["oee"]).pvalue) if n > 1 and np.std(d_oee) > 0 else float("nan")
    neto = e["beneficio_neto_anual"].to_numpy()
    m_neto, h_neto = intervalo_confianza(neto)
    inv = float(e["inversion_inicial"].mean())
    d_par = float((a["paradas_no_planificadas_h"].to_numpy() - e["paradas_no_planificadas_h"].to_numpy()).mean())
    c_par = float(eco["costo_hora_parada"])
    umbral_0 = c_par - m_neto / d_par if d_par > 0 else float("nan")
    umbral_12 = c_par + (inv - m_neto) / d_par if d_par > 0 else float("nan")
    return dict(
        d_oee=m_oee, h_oee=h_oee, p=p_val, oee=float(e["oee"].mean()), oee_asis=float(a["oee"].mean()),
        neto=m_neto, h_neto=h_neto, inversion=inv, recuperacion=inv / (m_neto / 12) if m_neto > 0 else math.inf,
        d_paradas=d_par, d_fallas=float((a["fallas"].to_numpy() - e["fallas"].to_numpy()).mean()),
        d_lotes=float((a["lotes_retrasados"].to_numpy() - e["lotes_retrasados"].to_numpy()).mean()),
        c_par=c_par, umbral_0=umbral_0, umbral_12=umbral_12, n=n)


def panel_comprobacion(c, nombre="TPM + IoT"):
    st.subheader(f"Comprobación: ¿{nombre} mejora la eficiencia y tiene beneficio?", help=AYUDA["comprobacion"])
    mejora = c["d_oee"] > 0 and (c["p"] < 0.05 if not math.isnan(c["p"]) else c["d_oee"] - c["h_oee"] > 0)
    if mejora:
        v1 = (C["ok"], "Sí, mejora la eficiencia")
    else:
        v1 = (C["bad"], "No se demuestra una mejora")
    p_txt = "p < 0.001" if c["p"] < 0.001 else f"p = {c['p']:.3f}"
    if c["neto"] > 0 and c["neto"] - c["h_neto"] > 0:
        v2 = (C["ok"], "Sí, tiene beneficio neto")
    elif c["neto"] > 0:
        v2 = (C["warn"], "Beneficio positivo, pero incierto")
    else:
        v2 = (C["bad"], "No, con los costos ingresados")
    rec = "no se recupera" if math.isinf(c["recuperacion"]) else f"{c['recuperacion']:.1f} meses"
    col1, col2 = st.columns(2)
    col1.markdown(f"""<div class="cbi-veredicto" style="border-color:{v1[0]}">
      <div class="t">1 · Eficiencia (OEE)</div><div class="r" style="color:{v1[0]}">{v1[1]}</div>
      <p>OEE de <b>{pct(c['oee_asis'])}</b> a <b>{pct(c['oee'])}</b>: <b>{100 * c['d_oee']:+.1f} pp</b>
      (IC 95 % ±{100 * c['h_oee']:.1f} pp; prueba t pareada, {p_txt}, {c['n']} réplicas).</p>
      <p>Paradas evitadas: <b>{c['d_paradas']:,.0f} h/año</b> · fallas evitadas: <b>{c['d_fallas']:.0f}</b> ·
      lotes retrasados evitados: <b>{c['d_lotes']:.0f}</b>.</p></div>""", unsafe_allow_html=True)
    umbral = ""
    if not math.isnan(c["umbral_0"]):
        if c["neto"] <= 0:
            umbral = (f"<p>El beneficio se vuelve positivo si la hora de parada cuesta <b>≥ S/ {c['umbral_0']:,.0f}</b> "
                      f"(hoy se usa S/ {c['c_par']:,.0f}).</p>")
        umbral += (f"<p>Para recuperar la inversión en 12 meses o menos, la hora de parada debe costar "
                   f"<b>≥ S/ {c['umbral_12']:,.0f}</b>.</p>")
    col2.markdown(f"""<div class="cbi-veredicto" style="border-color:{v2[0]}">
      <div class="t">2 · Beneficio económico (anual)</div><div class="r" style="color:{v2[0]}">{v2[1]}</div>
      <p>Beneficio neto: <b>{soles(c['neto'])}/año</b> (IC 95 % ±S/ {c['h_neto']:,.0f}) · inversión:
      <b>{soles(c['inversion'])}</b> · recuperación: <b>{rec}</b>.</p>{umbral}</div>""", unsafe_allow_html=True)
    st.caption("Los costos son supuestos editables en la barra lateral. El costo por hora de parada debe incluir "
               "la producción que se deja de vender; reemplácelo por el valor real de CBI Perú.")


# ------------------------------------------------------------------ barra lateral
p_cal, hist_cal = parametros_calibrados()
print("SimTI: modelo calibrado", flush=True)
st.sidebar.markdown("### ⚙️ SimTI-CBI")
st.sidebar.caption("R2 · Modelo integrado TPM + IoT · CBI Perú")
perfil = st.sidebar.radio("Perfil", ["Jefe de mantenimiento", "Técnico de mantenimiento"],
                          help="Cambia la interfaz según el usuario. El jefe ve indicadores, validación y simulación; "
                               "el técnico ve sus órdenes, las alertas y el checklist. No es un inicio de sesión.")
ES_JEFE = perfil.startswith("Jefe")
if ES_JEFE:
    VISTAS = [
        ("Inicio · ¿Cómo funciona?", "General"),
        ("IoT · Monitoreo de máquinas", "Planta · datos registrados"),
        ("TPM · Gestión del mantenimiento", "Planta · datos registrados"),
        ("Ficha de máquina · IoT + TPM", "Planta · datos registrados"),
        ("Indicadores desde registros", "Planta · datos registrados"),
        ("Situación actual (AS-IS)", "Modelo · simulación"),
        ("Simulador de escenarios", "Modelo · simulación"),
        ("Comparación y decisión", "Modelo · simulación"),
        ("Validación del modelo", "Modelo · simulación"),
    ]
else:
    VISTAS = [
        ("Mis órdenes de trabajo", "TPM · lo que debo hacer"),
        ("Checklist de mantenimiento autónomo", "TPM · inspección diaria"),
        ("Alertas de las máquinas", "IoT · qué revisar"),
        ("Ficha de máquina · IoT + TPM", "Equipo por equipo"),
        ("¿Qué miden los sensores?", "IoT · guía rápida"),
    ]
vista = st.sidebar.radio("Sección", [v for v, _ in VISTAS], captions=[c for _, c in VISTAS])
tecnico = "" if ES_JEFE else st.sidebar.text_input("Nombre del técnico", placeholder="Ej.: J. Pérez",
                                                   help="Se guarda en las órdenes que registre.")
st.sidebar.divider()

fuente = st.sidebar.radio("Fuente de datos de planta", ["Ejemplo sintético", "Excel de CBI"],
                          help=AYUDA["fuente"])
registros, errores_reg, contenido_reg = None, [], None
if fuente == "Excel de CBI":
    archivo = st.sidebar.file_uploader("Libro de registros (.xlsx)", type=["xlsx"])
    if archivo is not None:
        contenido_reg = archivo.getvalue()
        registros, errores_reg = leer_registros(contenido_reg)
    else:
        errores_reg = ["Suba el libro de registros de CBI (plantilla en el botón de abajo)."]
else:
    contenido_reg = (CARPETA_DATOS / "ejemplo_sintetico_CBI.xlsx").read_bytes()
    registros, errores_reg = leer_registros(contenido_reg)
if ES_JEFE:
    st.sidebar.download_button("⬇ Plantilla Excel para CBI", (CARPETA_DATOS / "plantilla_registros_CBI.xlsx").read_bytes(),
                               "plantilla_registros_CBI.xlsx", use_container_width=True)
    st.sidebar.download_button("⬇ Ejemplo sintético", (CARPETA_DATOS / "ejemplo_sintetico_CBI.xlsx").read_bytes(),
                               "ejemplo_sintetico_CBI.xlsx", use_container_width=True)
if errores_reg:
    for e in errores_reg:
        st.sidebar.warning(e)

eco = dict(p_cal["economicos"])
nivel, n_rep = "base", 20
if ES_JEFE:
    st.sidebar.divider()
    with st.sidebar.expander("Parámetros del modelo"):
        nivel = st.selectbox("Nivel de los parámetros de mejora", ["base", "pesimista", "optimista"],
                             help="Valores de la literatura y supuestos (tabla de parámetros del escenario).")
        n_rep = st.slider("Réplicas por escenario", 5, 50, 20, 5,
                          help="Más réplicas = intervalos de confianza más estrechos. 20 es suficiente.")
    with st.sidebar.expander("Supuestos económicos (editables)"):
        for clave, etiqueta, ayuda in [
            ("costo_hora_parada", "Costo por hora de parada (S/)",
             "Operadores en espera, energía, horas extra y producción que se deja de vender por cada hora de parada."),
            ("costo_hora_tecnico", "Costo hora técnico (S/)", None),
            ("costo_lote_retrasado", "Costo por lote retrasado (S/)", None),
            ("costo_compra_urgente", "Sobrecosto por compra urgente (S/)", None),
            ("costo_sensor_equipo", "Sensores por equipo (S/)", "Kit de vibración, temperatura y corriente."),
            ("costo_pasarela", "Pasarela IoT (S/)", None),
            ("costo_plataforma_mes", "Plataforma IoT (S/ por mes)", None),
            ("costo_capacitacion_tpm", "Capacitación TPM (S/)", None),
            ("costo_materiales_preventivo", "Materiales por orden preventiva (S/)", None),
        ]:
            eco[clave] = st.number_input(etiqueta, min_value=0.0, value=float(eco[clave]), step=5.0, help=ayuda)
eco_items = tuple(sorted(eco.items()))
niv_base = niveles_escenario(p_cal, nivel)
niv_items = tuple(sorted(niv_base.items()))
techo = techo_planta(p_cal["lineas"])


# ------------------------------------------------------------------ registros del técnico (sesión)
CLAVE_SESION = f"ejecuciones::{fuente}::{hash(contenido_reg) if contenido_reg else 0}"
sesion = st.session_state.setdefault(CLAVE_SESION, {"ejecuciones": {}, "nuevas": []})


def aplicar_ediciones(reg):
    """Incorpora a los registros las órdenes que el técnico registró en esta sesión."""
    if reg is None:
        return None
    pv = reg.preventivos.copy()
    if "estado" not in pv:
        pv["estado"] = pd.Series(dtype=str)
    for c in ("ejecutado_por", "observacion", "estado"):
        if c in pv:
            pv[c] = pv[c].astype(object)
    hora = float(reg.config.get("hora_inicio_turno", 7.0))
    for ot, e in sesion["ejecuciones"].items():
        m = pv["id_orden"] == ot
        pv.loc[m, "inicio_ejecucion"] = pd.Timestamp(e["fecha"]) + pd.Timedelta(hours=hora)
        pv.loc[m, "ejecutado_por"] = e["por"]
        pv.loc[m, "observacion"] = e["obs"]
        pv.loc[m, "estado"] = "Realizada"
    if sesion["nuevas"]:
        pv = pd.concat([pv, pd.DataFrame(sesion["nuevas"])], ignore_index=True)
    return dataclasses.replace(reg, preventivos=pv)


registros = aplicar_ediciones(registros)
eq_modelo = p_cal["equipos"]
nombre_eq = dict(zip(eq_modelo["codigo"], eq_modelo["descripcion"]))


def aviso_fuente(reg):
    if reg is None:
        return
    periodo = (f"{reg.calendario.inicio.astype('datetime64[D]').item():%d/%m/%Y} – "
               f"{reg.fecha_corte:%d/%m/%Y}")
    if reg.sintetico:
        banner(f"<b>Datos sintéticos</b> generados con el simulador para probar la herramienta ({periodo}). "
               "No son datos de CBI Perú ni lecturas de sensores físicos.", "sint")
    else:
        banner(f"<b>Datos cargados:</b> {html.escape(str(reg.config.get('naturaleza_datos')))} · periodo {periodo}.",
               "real")
    for a in reg.avisos:
        st.warning(a)


def requiere_registros():
    if registros is None:
        st.error("No hay registros de planta válidos para esta sección.")
        for e in errores_reg:
            st.write("• " + e)
        st.info("Descargue la plantilla Excel desde la barra lateral, complétela y súbala en «Excel de CBI», "
                "o cambie la fuente a «Ejemplo sintético».")
        st.stop()


def kpi_equipos(reg):
    t = kpi_por_equipo(reg.eventos, reg.lotes).set_index("codigo_equipo")
    return t


# ================================================================== VISTAS
def v_inicio():
    st.title("SimTI-CBI · R2 TPM + IoT")
    st.markdown("Herramienta del modelo integrado **TPM + IoT** para mejorar la eficiencia operativa (OEE) de "
                "CBI Perú: **monitorea** las máquinas con sensores, **gestiona** su mantenimiento y **simula** "
                "cuánto mejora el OEE y cuánto cuesta implementarlo.")
    st.subheader("¿Cómo funciona?", help="Flujo de la solución: IoT detecta, TPM actúa y los indicadores miden.")
    pasos = [
        (C["iot"], "1 · Sensores IoT", "Miden vibración, temperatura y corriente en los equipos críticos."),
        (C["iot"], "2 · Alerta", "Una lectura que supera su límite avisa de una condición anormal."),
        (C["tpm"], "3 · Orden de trabajo", "TPM programa la intervención antes de que el equipo falle."),
        (C["tpm"], "4 · Mantenimiento", "Plan preventivo, mantenimiento autónomo y reparación estándar."),
        ("#334155", "5 · Indicadores", "OEE, disponibilidad, MTBF y MTTR muestran el resultado."),
    ]
    flujo = '<div class="cbi-flow">'
    for i, (col, t, d) in enumerate(pasos):
        flujo += f'<div class="cbi-step" style="background:{col}"><b>{t}</b><span>{d}</span></div>'
        if i < len(pasos) - 1:
            flujo += '<div class="cbi-arrow" aria-hidden="true">→</div>'
    st.markdown(flujo + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"#### {ICONO['maquina']} Planta · datos registrados", unsafe_allow_html=True)
        st.markdown("- **IoT · Monitoreo:** estado de sensores, lecturas, tendencias y alertas.\n"
                    "- **TPM · Gestión:** plan preventivo, órdenes realizadas, vencidas y pendientes.\n"
                    "- **Ficha de máquina:** IoT y TPM de un mismo equipo en una pantalla.\n"
                    "- **Indicadores:** OEE, MTBF y MTTR calculados desde los registros.")
        st.caption("Fuente: libro Excel de registros (de CBI o el ejemplo sintético).")
    with c2, st.container(border=True):
        st.markdown("#### 📈 Modelo · simulación para decidir")
        st.markdown("- **Situación actual:** la planta de hoy reproducida por el modelo.\n"
                    "- **Simulador:** pruebe TPM, IoT o ambos y compruebe la mejora del OEE y el beneficio.\n"
                    "- **Comparación y decisión:** las 4 combinaciones del diseño 2² (TPM × IoT).\n"
                    "- **Validación:** el modelo frente a la línea base y sus pruebas.")
        st.caption("Fuente: parámetros del diagnóstico (Capítulo III), literatura y supuestos declarados.")

    st.subheader("Estado de los datos de planta", help=AYUDA["fuente"])
    if registros is None:
        st.warning("Sin registros válidos. " + " ".join(errores_reg))
    else:
        aviso_fuente(registros)
        m = st.columns(5)
        m[0].metric("Paradas registradas", f"{len(registros.eventos):,}")
        m[1].metric("Lotes", f"{len(registros.lotes):,}")
        m[2].metric("Órdenes TPM", f"{len(registros.preventivos):,}")
        m[3].metric("Sensores IoT", f"{len(registros.sensores):,}")
        m[4].metric("Lecturas IoT", f"{len(registros.lecturas):,}")
    with st.expander("¿Cómo carga CBI sus datos reales?"):
        st.markdown("1. Descargue la **plantilla Excel** en la barra lateral.\n"
                    "2. Complete *Configuracion* (turno) y revise *Equipos*.\n"
                    "3. Registre **Paradas** y **Lotes** (obligatorias); **Preventivos** para TPM; **Sensores**, "
                    "**Lecturas_IoT** y **Alertas_IoT** para IoT (opcionales).\n"
                    "4. En la barra lateral elija **Excel de CBI** y suba el archivo. La hoja *LEEME* explica cada columna.")


def v_iot():
    requiere_registros()
    reg = registros
    st.title("IoT · Monitoreo de máquinas", help=AYUDA["iot"])
    aviso_fuente(reg)
    if not reg.tiene_iot:
        st.info("El libro no tiene la hoja «Sensores» con datos. Complete *Sensores* y *Lecturas_IoT* para ver "
                "esta sección.")
        return
    es = estado_sensores(reg.sensores, reg.lecturas, reg.fecha_corte)
    kp = kpi_equipos(reg)
    pv = reg.preventivos
    al = reg.alertas
    eq_sens = list(dict.fromkeys(reg.sensores["codigo_equipo"]))
    m = st.columns(4)
    m[0].metric("Máquinas monitoreadas", f"{len(eq_sens)} de {len(reg.equipos)}",
                help="Equipos con al menos un sensor registrado en la hoja «Sensores».")
    m[1].metric("Sensores transmitiendo", f"{int((es['transmision'] == 'Transmitiendo').sum())} de {len(es)}",
                help=AYUDA["transmision"])
    m[2].metric("Lecturas fuera de límite", f"{int(es['fuera_limite'].sum()):,}", help=AYUDA["fuera_limite"])
    m[3].metric("Alertas registradas", f"{len(al):,}", help=AYUDA["alertas"])

    t1, t2, t3, t4 = st.tabs(["Máquinas monitoreadas", "Tendencias de sensores", "Alertas → órdenes TPM",
                              "¿Qué miden los sensores?"])
    with t4:
        guia_sensores(reg)
    with t1:
        st.caption(f"Estado a la fecha de corte: {reg.fecha_corte:%d/%m/%Y %H:%M}.")
        tarjetas = '<div class="cbi-grid">'
        for cod in eq_sens:
            s = es[es["codigo_equipo"] == cod]
            if (s["condicion"] == "Fuera de límite").any():
                est = badge("Requiere atención", "b-bad")
            elif (s["transmision"] != "Transmitiendo").any():
                est = badge("Sin datos recientes", "b-gris")
            else:
                est = badge("Normal", "b-ok")
            filas = ""
            for r in s.itertuples():
                color = C["ok"] if r.transmision == "Transmitiendo" else C["gris"]
                lim = "" if pd.isna(r.limite_alerta) else f" / {r.limite_alerta:g}"
                val = "—" if pd.isna(r.ultimo_valor) else f"{r.ultimo_valor:g}"
                alerta = ' <span style="color:#B91C1C">▲</span>' if r.condicion == "Fuera de límite" else ""
                inf = info_variable(r.variable)
                ayuda_var = tip(f"Mide: {inf['mide']} Detecta: {inf['detecta']}") if inf else ""
                filas += (f'<div class="cbi-row"><span><span class="dot" style="background:{color}" '
                          f'title="{html.escape(r.transmision)}"></span>{html.escape(str(r.variable))}&nbsp;{ayuda_var}</span>'
                          f'<span class="v">{val}{lim} {html.escape(str(r.unidad))}{alerta}</span></div>')
            n_al = int((al["codigo_equipo"] == cod).sum()) if not al.empty else 0
            n_ot = int(((pv["codigo_equipo"] == cod) & pv["origen"].str.contains("IoT", na=False)).sum()) if not pv.empty else 0
            disp = kp["disponibilidad"].get(cod, float("nan"))
            tarjetas += (f'<div class="cbi-card iot"><h4>{ICONO["sensor"]}{html.escape(cod)}</h4>'
                         f'<div class="sub">{html.escape(nombre_eq.get(cod, ""))}</div>'
                         f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">{est}'
                         f'{tip(AYUDA["condicion"])}</div>{filas}'
                         f'<div class="cbi-foot"><span>Alertas: <b>{n_al}</b></span><span>OT por alerta: <b>{n_ot}</b></span>'
                         f'<span>Disponibilidad: <b>{pct(disp)}</b></span></div></div>')
        st.markdown(tarjetas + "</div>", unsafe_allow_html=True)
        st.caption("● verde = transmitiendo · ● gris = sin datos recientes · ▲ = última lectura fuera de límite. "
                   "Valores: última lectura / límite de alerta.")
        sin = [c for c in reg.equipos["codigo"] if c not in eq_sens]
        if sin:
            st.caption("Equipos sin sensor: " + ", ".join(sin))
    with t2:
        if reg.lecturas.empty:
            st.info("No hay lecturas en la hoja «Lecturas_IoT».")
        else:
            c1, c2 = st.columns([2, 1])
            cod = c1.selectbox("Máquina", eq_sens, format_func=lambda c: f"{c} · {nombre_eq.get(c, '')}")
            periodo = c2.selectbox("Periodo", ["Últimos 30 días", "Últimos 90 días", "Todo el periodo"])
            dias = {"Últimos 30 días": 30, "Últimos 90 días": 90}.get(periodo)
            figura_tendencias(reg, cod, dias)
    with t3:
        st.markdown("Cada alerta anticipada genera una **orden de trabajo TPM** que se ejecuta sin detener el lote. "
                    + tip(AYUDA["ot_iot"]), unsafe_allow_html=True)
        if al.empty:
            st.info("No hay alertas en la hoja «Alertas_IoT».")
        else:
            cont = al["tipo"].value_counts()
            c = st.columns(3)
            c[0].metric("Anticipadas → OT", int(cont.get("anticipada", 0)),
                        help="Llegaron a tiempo: se programó una orden de trabajo sin parar el equipo.")
            c[1].metric("Tardías", int(cont.get("tardía", 0)),
                        help="La falla ocurrió, pero el técnico fue avisado antes que por correo.")
            c[2].metric("Falsas", int(cont.get("falsa", 0)), help="Se revisó y no había falla. Consumen horas de técnico.")
            t = al.merge(pv[["id_alerta", "id_orden", "estado", "inicio_ejecucion"]] if not pv.empty else
                         pd.DataFrame(columns=["id_alerta", "id_orden", "estado", "inicio_ejecucion"]),
                         on="id_alerta", how="left")
            t = t.sort_values("fecha_hora", ascending=False)
            st.dataframe(t[["fecha_hora", "id_alerta", "codigo_equipo", "sensor_id", "tipo", "resultado", "id_orden",
                            "estado", "inicio_ejecucion"]].rename(columns={
                "fecha_hora": "Fecha", "id_alerta": "Alerta", "codigo_equipo": "Equipo", "sensor_id": "Sensor",
                "tipo": "Tipo", "resultado": "Resultado", "id_orden": "OT TPM", "estado": "Estado OT",
                "inicio_ejecucion": "Ejecución OT"}),
                use_container_width=True, hide_index=True,
                column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                               "Ejecución OT": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})


def figura_tendencias(reg, cod, dias=None, compacta=False):
    sens = reg.sensores[reg.sensores["codigo_equipo"] == cod]
    lec = reg.lecturas
    hasta = pd.Timestamp(reg.fecha_corte)
    desde = hasta - pd.Timedelta(days=dias) if dias else lec["fecha_hora"].min()
    al = reg.alertas[(reg.alertas["codigo_equipo"] == cod) & (reg.alertas["fecha_hora"] >= desde)] \
        if not reg.alertas.empty else pd.DataFrame()
    fig, axes = plt.subplots(len(sens), 1, figsize=(10, (1.6 if compacta else 2.1) * len(sens) + 0.4),
                             sharex=True, squeeze=False)
    colores_al = {"anticipada": C["iot"], "tardía": C["warn"], "falsa": C["gris"]}
    for ax, s in zip(axes[:, 0], sens.itertuples()):
        d = lec[(lec["sensor_id"] == s.sensor_id) & (lec["fecha_hora"] >= desde)]
        ax.plot(d["fecha_hora"], d["valor"], color=C["iot"], lw=1)
        if pd.notna(s.limite_alerta):
            ax.axhline(s.limite_alerta, color=C["bad"], ls="--", lw=1)
            fuera = d[d["valor"] > s.limite_alerta]
            ax.scatter(fuera["fecha_hora"], fuera["valor"], color=C["bad"], s=12, zorder=3)
        for a in al.itertuples() if not al.empty else []:
            if a.sensor_id == s.sensor_id:
                ax.axvline(a.fecha_hora, color=colores_al.get(a.tipo, C["gris"]), lw=0.9, alpha=0.7)
        ax.set_title(f"{s.variable} ({s.unidad})", fontsize=9.5)
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption("— lectura · - - límite de alerta · ● lectura fuera de límite · líneas verticales: alertas "
               "(azul = anticipada, naranja = tardía, gris = falsa).")


def v_tpm():
    requiere_registros()
    reg = registros
    st.title("TPM · Gestión del mantenimiento", help=AYUDA["tpm"])
    aviso_fuente(reg)
    if not reg.tiene_tpm:
        st.info("El libro no tiene órdenes en la hoja «Preventivos». Complétela para ver esta sección.")
        return
    pv = reg.preventivos
    cont = pv["estado"].value_counts()
    hechas, venc, pend = int(cont.get("Realizada", 0)), int(cont.get("Vencida", 0)), int(cont.get("Pendiente", 0))
    cumpl = hechas / (hechas + venc) if hechas + venc else float("nan")
    por_iot = int(pv["origen"].str.contains("IoT", na=False).sum())
    m = st.columns(5)
    m[0].metric("Cumplimiento del plan", pct(cumpl), help=AYUDA["cumplimiento"])
    m[1].metric("Realizadas", f"{hechas:,}", help="Órdenes con fecha de ejecución hasta la fecha de corte.")
    m[2].metric("Vencidas", f"{venc:,}", help=AYUDA["vencidas"])
    m[3].metric("Pendientes", f"{pend:,}", help=AYUDA["pendientes"])
    m[4].metric("OT originadas por IoT", f"{por_iot:,}", help=AYUDA["ot_iot"])
    st.caption(f"Fecha de corte: {reg.fecha_corte:%d/%m/%Y}. Cumplimiento de referencia del diagnóstico: 38,6 %.")

    t1, t2, t3 = st.tabs(["Por máquina", "Actividades de mantenimiento", "Validación de TPM"])
    with t3:
        validacion_tpm(reg)
    with t1:
        rt = resumen_tpm(pv).set_index("codigo_equipo")
        kp = kpi_equipos(reg)
        clase = reg.equipos.set_index("codigo")["clase_a"]
        sensor = reg.equipos.set_index("codigo")["sensor_iot"]
        tabla = rt.join(kp[["disponibilidad", "fallas", "mtbf_h", "mttr_h"]], how="left")
        tabla.insert(0, "Equipo", [f"{c} · {nombre_eq.get(c, '')}" for c in tabla.index])
        tabla.insert(1, "Clase A", ["Sí" if clase.get(c, 0) else "No" for c in tabla.index])
        tabla.insert(2, "Sensor IoT", ["Sí" if sensor.get(c, 0) else "No" for c in tabla.index])
        tabla = tabla.sort_values("cumplimiento")
        st.dataframe(tabla, hide_index=True, use_container_width=True, column_config={
            "cumplimiento": st.column_config.ProgressColumn("Cumplimiento", format="%.0f%%", min_value=0, max_value=1,
                                                            help=AYUDA["cumplimiento"]),
            "Realizada": st.column_config.NumberColumn("Realizadas"),
            "Vencida": st.column_config.NumberColumn("Vencidas", help=AYUDA["vencidas"]),
            "Pendiente": st.column_config.NumberColumn("Pendientes", help=AYUDA["pendientes"]),
            "por_alerta": st.column_config.NumberColumn("OT por alerta IoT", help=AYUDA["ot_iot"]),
            "disponibilidad": st.column_config.NumberColumn("Disponibilidad", format="%.2f",
                                                            help=AYUDA["disponibilidad"]),
            "fallas": st.column_config.NumberColumn("Fallas"),
            "mtbf_h": st.column_config.NumberColumn("MTBF (h)", format="%.1f", help=AYUDA["mtbf"]),
            "mttr_h": st.column_config.NumberColumn("MTTR (h)", format="%.1f", help=AYUDA["mttr"]),
        })
        st.caption("La barra de cumplimiento muestra la fracción del plan ejecutada; disponibilidad, fallas, MTBF y "
                   "MTTR salen de las hojas Paradas y Lotes. Ordenado de menor a mayor cumplimiento.")
    with t2:
        c1, c2, c3 = st.columns([1.2, 1.4, 1.2])
        estado = c1.radio("Estado", ["Pendiente", "Vencida", "Realizada", "Todas"], horizontal=True,
                          help="Pendiente: aún no vence · Vencida: pasó su fecha sin ejecutarse · Realizada: ejecutada.")
        equipos = c2.multiselect("Equipos", sorted(pv["codigo_equipo"].unique()))
        origen = c3.multiselect("Origen", sorted(pv["origen"].unique()),
                                help="Plan preventivo, alerta IoT o mantenimiento autónomo.")
        t = pv.copy()
        if estado != "Todas":
            t = t[t["estado"] == estado]
        if equipos:
            t = t[t["codigo_equipo"].isin(equipos)]
        if origen:
            t = t[t["origen"].isin(origen)]
        t = t.sort_values("fecha_programada", ascending=estado in ("Pendiente",))
        colores = {"Realizada": "#DCFCE7", "Vencida": "#FEE2E2", "Pendiente": "#FEF3C7"}
        vista_t = t[["id_orden", "codigo_equipo", "actividad", "origen", "id_alerta", "fecha_programada",
                     "inicio_ejecucion", "estado"]].rename(columns={
            "id_orden": "OT", "codigo_equipo": "Equipo", "actividad": "Actividad", "origen": "Origen",
            "id_alerta": "Alerta IoT", "fecha_programada": "Programada", "inicio_ejecucion": "Ejecutada",
            "estado": "Estado"})
        st.dataframe(vista_t.style.map(lambda v: f"background-color:{colores.get(v, '')}", subset=["Estado"]),
                     hide_index=True, use_container_width=True,
                     column_config={"Programada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                                    "Ejecutada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
        st.caption(f"{len(t)} órdenes. Las de origen «Alerta IoT» enlazan con la sección IoT por el código de alerta.")
        boton_libro_actualizado(reg)


def v_ficha():
    requiere_registros()
    reg = registros
    st.title("Ficha de máquina · IoT + TPM", help=AYUDA["ficha"])
    aviso_fuente(reg)
    codigos = list(reg.equipos["codigo"])
    con_sensor = set(reg.sensores["codigo_equipo"]) if reg.tiene_iot else set()
    cod = st.selectbox("Máquina", codigos, format_func=lambda c: f"{c} · {nombre_eq.get(c, '')}"
                       + ("  · con sensor" if c in con_sensor else ""))
    kp = kpi_equipos(reg)
    k = kp.loc[cod] if cod in kp.index else None
    pv = reg.preventivos[reg.preventivos["codigo_equipo"] == cod] if reg.tiene_tpm else pd.DataFrame()
    al = reg.alertas[reg.alertas["codigo_equipo"] == cod] if not reg.alertas.empty else pd.DataFrame()
    ev = reg.eventos[(reg.eventos["codigo_equipo"] == cod) & (reg.eventos["tipo"] == "falla_tecnica")]

    m = st.columns(4)
    m[0].metric("Disponibilidad", pct(k["disponibilidad"]) if k is not None else "—", help=AYUDA["disponibilidad"])
    m[1].metric("Fallas técnicas", f"{int(k['fallas'])}" if k is not None else "—")
    m[2].metric("MTBF", num(k["mtbf_h"], 1, " h") if k is not None else "—", help=AYUDA["mtbf"])
    m[3].metric("MTTR", num(k["mttr_h"], 1, " h") if k is not None else "—", help=AYUDA["mttr"])

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown(f"##### {ICONO['sensor']} IoT · lo que detecta el sensor", unsafe_allow_html=True)
            if cod not in con_sensor:
                st.caption("Este equipo no tiene sensores registrados.")
            else:
                es = estado_sensores(reg.sensores[reg.sensores["codigo_equipo"] == cod], reg.lecturas, reg.fecha_corte)
                st.dataframe(es[["variable", "ultimo_valor", "limite_alerta", "condicion", "transmision", "fuera_limite"]]
                             .rename(columns={"variable": "Variable", "ultimo_valor": "Última", "limite_alerta": "Límite",
                                              "condicion": "Condición", "transmision": "Transmisión",
                                              "fuera_limite": "Lecturas fuera"}),
                             hide_index=True, use_container_width=True,
                             column_config={"Condición": st.column_config.TextColumn(help=AYUDA["condicion"]),
                                            "Transmisión": st.column_config.TextColumn(help=AYUDA["transmision"])})
                st.caption(f"Alertas del periodo: {len(al)} (anticipadas {int((al['tipo'] == 'anticipada').sum()) if len(al) else 0}).")
    with c2:
        with st.container(border=True):
            st.markdown(f"##### {ICONO['llave']} TPM · lo que hace mantenimiento", unsafe_allow_html=True)
            if pv.empty:
                st.caption("Sin órdenes registradas para este equipo.")
            else:
                cont = pv["estado"].value_counts()
                h, v, p_ = int(cont.get("Realizada", 0)), int(cont.get("Vencida", 0)), int(cont.get("Pendiente", 0))
                st.markdown(f"{badge(f'Realizadas {h}', 'b-ok')} {badge(f'Vencidas {v}', 'b-bad')} "
                            f"{badge(f'Pendientes {p_}', 'b-warn')} "
                            f"{badge('OT por alerta ' + str(int(pv['origen'].str.contains('IoT', na=False).sum())), 'b-iot')}",
                            unsafe_allow_html=True)
                prox = pv[pv["estado"] != "Realizada"].sort_values("fecha_programada").head(5)
                st.dataframe(prox[["id_orden", "actividad", "fecha_programada", "estado"]].rename(columns={
                    "id_orden": "OT", "actividad": "Actividad", "fecha_programada": "Programada", "estado": "Estado"}),
                    hide_index=True, use_container_width=True,
                    column_config={"Programada": st.column_config.DatetimeColumn(format="DD/MM/YYYY")})
                st.caption("Próximas órdenes pendientes y vencidas.")
    if cod in con_sensor and not reg.lecturas.empty:
        st.subheader("Tendencias de los últimos 30 días")
        figura_tendencias(reg, cod, 30, compacta=True)

    st.subheader("Historial: alerta → orden de trabajo → falla",
                 help="Línea de tiempo del equipo. Permite ver si una alerta terminó en una OT programada o en una falla.")
    cal = reg.calendario
    filas = []
    for a in al.itertuples() if len(al) else []:
        filas.append(dict(Fecha=a.fecha_hora, Origen="IoT", Evento=f"Alerta {a.tipo}", Detalle=f"{a.id_alerta} · {a.sensor_id} · {a.resultado}"))
    for o in pv.itertuples() if len(pv) else []:
        if pd.notna(o.inicio_ejecucion):
            filas.append(dict(Fecha=o.inicio_ejecucion, Origen="TPM", Evento="OT realizada",
                              Detalle=f"{o.id_orden} · {o.actividad}" + (f" · alerta {o.id_alerta}" if o.id_alerta else "")))
    for f in ev.itertuples():
        filas.append(dict(Fecha=pd.Timestamp(cal.a_fecha(f.inicio_parada_h)), Origen="Planta", Evento="Falla técnica",
                          Detalle=f"{f.categoria} · {f.fin_parada_h - f.inicio_parada_h:.1f} h de parada"))
    if filas:
        h = pd.DataFrame(filas).sort_values("Fecha", ascending=False).head(40)
        st.dataframe(h, hide_index=True, use_container_width=True,
                     column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
    else:
        st.caption("Sin eventos para este equipo.")


def v_indicadores():
    requiere_registros()
    reg = registros
    st.title("Indicadores desde registros", help="Calcula OEE, disponibilidad, MTBF y MTTR con las hojas Paradas y "
             "Lotes del libro Excel (estructura ISO 14224).")
    aviso_fuente(reg)
    k, pl = kpi_desde_registros(reg.eventos, reg.lotes, p_cal["lineas"])
    m = st.columns(5)
    m[0].metric("OEE", pct(k["oee"]), help=AYUDA["oee"] + " Rendimiento y calidad se toman de la línea base.")
    m[1].metric("Disponibilidad", pct(k["disponibilidad"]), help=AYUDA["disponibilidad"])
    m[2].metric("MTBF", num(k["mtbf_h"], 1, " h"), help=AYUDA["mtbf"])
    m[3].metric("MTTR", num(k["mttr_h"], 1, " h"), help=AYUDA["mttr"])
    m[4].metric("Respuesta mediana", num(k["respuesta_mediana_min"], 0, " min"),
                help="Mediana del tiempo entre la parada y la llegada del técnico.")
    evf = reg.eventos[reg.eventos.tipo == "falla_tecnica"].assign(d=lambda x: x.fin_parada_h - x.inicio_parada_h)
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Horas de parada técnica por equipo**")
        st.bar_chart(evf.groupby("codigo_equipo")["d"].sum().sort_values(ascending=False), color=C["tpm"])
    with g2:
        st.markdown("**OEE por línea**")
        st.bar_chart(pl.set_index("linea")["oee"], color=C["iot"])
    st.subheader("Ajuste de distribuciones del tiempo entre fallas",
                 help="Ajuste Weibull por equipo con prueba de Kolmogorov–Smirnov (aceptado si p > 0,05). Con datos "
                      "reales, estos valores reemplazan a los supuestos del simulador.")
    st.dataframe(ajustar_weibull(reg.eventos).round(3), use_container_width=True, hide_index=True)


def v_asis():
    st.title("Situación actual (AS-IS)", help="La planta de hoy reproducida por el modelo calibrado, con los "
             "parámetros del diagnóstico. Son los indicadores que CBI hoy no calcula.")
    kp, lineas, ev0 = corrida_asis(eco_items, n_rep)
    c = st.columns(5)
    c[0].metric("OEE de planta", pct(kp.oee.mean()), f"meta 85 % · brecha {100 * (META_OEE - kp.oee.mean()):.1f} pp",
                delta_color="off", help=AYUDA["oee"])
    c[1].metric("Disponibilidad", pct(kp.disponibilidad.mean()), help=AYUDA["disponibilidad"])
    c[2].metric("MTBF", f"{kp.mtbf_h.mean():.1f} h", help=AYUDA["mtbf"])
    c[3].metric("MTTR", f"{kp.mttr_h.mean():.1f} h", help=AYUDA["mttr"])
    c[4].metric("Paradas no planificadas", f"{kp.paradas_no_planificadas_h.mean():,.0f} h/año", help=AYUDA["paradas"])
    col1, col2 = st.columns(2)
    with col1:
        pl = lineas.groupby("linea", sort=False)[["oee", "techo_oee"]].mean()
        fig, ax = plt.subplots(figsize=(7, 3.6))
        y = np.arange(len(pl))
        ax.barh(y, 100 * pl["techo_oee"], color="#D9E6F2", label="Techo de OEE (disponibilidad 100 %)")
        ax.barh(y, 100 * pl["oee"], color=C["iot"], label="OEE actual")
        ax.axvline(85, color=C["bad"], ls="--", lw=1.2, label="Meta 85 %")
        ax.set_yticks(y, pl.index); ax.invert_yaxis(); ax.set_xlabel("%")
        ax.set_title("OEE por línea frente al techo y la meta")
        ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
        ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
        st.pyplot(fig); plt.close(fig)
    with col2:
        comp = pd.Series({"Respuesta": kp.mttr_respuesta_h.mean(), "Espera de repuesto": kp.mttr_espera_h.mean(),
                          "Reparación activa": kp.mttr_reparacion_h.mean()})
        fig = figura_barras_h(list(comp.index), list(comp.values), "¿De qué está hecho el MTTR?", "horas por falla",
                              color=[C["iot"], C["claro"], C["tpm"]])
        st.pyplot(fig); plt.close(fig)
        st.caption(f"IoT acorta la **respuesta** y TPM la **reparación**. La espera de repuesto "
                   f"({comp['Espera de repuesto'] / comp.sum():.0%} del MTTR) depende de compras y queda fuera del alcance de R2.")
    ev = ev0[ev0["tipo"] == "falla_tecnica"].assign(d=lambda x: x.fin_parada_h - x.inicio_parada_h)
    st.subheader("Pareto de horas de parada técnica por equipo (réplica 1)")
    st.bar_chart(ev.groupby("codigo_equipo")["d"].sum().sort_values(ascending=False), color=C["tpm"])


def v_simulador():
    st.title("Simulador de escenarios", help="Configure las acciones de R2, presione Simular y compruebe si mejoran "
             "el OEE y si tienen beneficio frente a la situación actual.")
    eq = eq_modelo
    clase_a = eq[eq.clase_a == 1]
    n_prog = int(clase_a["preventivos_anio"].sum())
    c_asis = float(p_cal["generales"]["cumplimiento_preventivo_asis"])
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"#### {ICONO['llave']} A · TPM", unsafe_allow_html=True)
        tpm = st.checkbox("Aplicar prácticas TPM", True, help=AYUDA["tpm_check"])
        cumpl_pct = st.slider("Cumplimiento del plan preventivo en equipos críticos (clase A)", 39, 100, 100, 1,
                              format="%d %%", disabled=not tpm, help=AYUDA["cumpl_slider"])
        cumpl = cumpl_pct / 100
        avance = (cumpl - c_asis) / (1 - c_asis)
        if tpm:
            st.markdown(
                f"- Se ejecutan **≈ {cumpl * n_prog:.0f} de {n_prog}** órdenes preventivas al año en los "
                f"{len(clase_a)} equipos clase A (hoy ≈ {c_asis * n_prog:.0f}).\n"
                f"- Efecto en el modelo: las fallas por desgaste se espacian **+{100 * niv_base['delta_tpm_mtbf'] * avance:.0f} %** "
                f"y la reparación es **{100 * niv_base['red_reparacion_tpm']:.0f} % más rápida**.\n"
                f"- Costo: ≈ {max(0, (cumpl - c_asis) * n_prog):.0f} órdenes extra × S/ {eco['costo_materiales_preventivo']:,.0f} "
                f"+ checklist autónomo diario de 15 min por equipo.")
            st.caption("Equipos clase A: " + ", ".join(clase_a["codigo"]))
    with c2, st.container(border=True):
        st.markdown(f"#### {ICONO['sensor']} B · IoT", unsafe_allow_html=True)
        iot = st.checkbox("Monitorear con sensores IoT", True, help=AYUDA["iot_check"])
        sensores = st.multiselect("Equipos con sensor", list(eq["codigo"]),
                                  default=list(eq.loc[eq.sensor_candidato == 1, "codigo"]), disabled=not iot,
                                  help=AYUDA["sensores"])
        if iot:
            n_s = len(sensores) or int((eq.sensor_candidato == 1).sum())
            st.markdown(
                f"- **{n_s} equipos** con sensores de vibración, temperatura y corriente.\n"
                f"- De las fallas con señales previas, se detecta el **{100 * niv_base['p_deteccion']:.0f} %**; "
                f"el **{100 * niv_base['frac_anticipada']:.0f} %** de las alertas llega a tiempo para programar la OT.\n"
                f"- Inversión: S/ {n_s * eco['costo_sensor_equipo'] + eco['costo_pasarela']:,.0f} + "
                f"S/ {eco['costo_plataforma_mes']:,.0f} al mes de plataforma.")
    n_tec = st.select_slider("Técnicos de mantenimiento", [1, 2, 3], 1, help=AYUDA["tecnicos"])
    with st.expander("Parámetros de mejora (literatura y supuestos)"):
        st.caption(f"Valores del nivel «{nivel}». Cámbielos solo para analizar sensibilidad: cada valor debe tener fuente.")
        niv = dict(niv_base)
        cc = st.columns(3)
        niv["delta_tpm_mtbf"] = cc[0].slider(NOMBRES_PARAM["delta_tpm_mtbf"], 0.0, 0.8, niv["delta_tpm_mtbf"], 0.05,
                                             help=AYUDA_PARAM["delta_tpm_mtbf"])
        niv["red_reparacion_tpm"] = cc[0].slider(NOMBRES_PARAM["red_reparacion_tpm"], 0.0, 0.7, niv["red_reparacion_tpm"],
                                                 0.05, help=AYUDA_PARAM["red_reparacion_tpm"])
        niv["p_deteccion"] = cc[1].slider(NOMBRES_PARAM["p_deteccion"], 0.0, 1.0, niv["p_deteccion"], 0.05,
                                          help=AYUDA_PARAM["p_deteccion"])
        niv["frac_anticipada"] = cc[1].slider(NOMBRES_PARAM["frac_anticipada"], 0.0, 1.0, niv["frac_anticipada"], 0.05,
                                              help=AYUDA_PARAM["frac_anticipada"])
        niv["red_respuesta_alerta"] = cc[2].slider(NOMBRES_PARAM["red_respuesta_alerta"], 0.0, 0.9,
                                                   niv["red_respuesta_alerta"], 0.05, help=AYUDA_PARAM["red_respuesta_alerta"])
        niv["falsas_alarmas_mes"] = cc[2].slider(NOMBRES_PARAM["falsas_alarmas_mes"], 0.0, 4.0, niv["falsas_alarmas_mes"],
                                                 0.5, help=AYUDA_PARAM["falsas_alarmas_mes"])
    niv["cumplimiento_preventivo_tobe"] = cumpl

    if st.button("▶ Simular", type="primary"):
        if not (tpm or iot):
            st.warning("Active al menos una acción (TPM o IoT).")
        else:
            p = con_economicos(p_cal, eco)
            nombre = {(True, True): "TPM + IoT", (True, False): "Solo TPM", (False, True): "Solo IoT"}[(tpm, iot)]
            esc = Escenario(nombre, tpm, iot, niv, n_tec, tuple(sensores))
            barra = st.progress(0.0, text="Simulando réplicas…")
            df, _ = correr(p, [esc], n_rep, progreso=lambda x: barra.progress(x, text="Simulando réplicas…"))
            barra.empty()
            asis = corrida_asis(eco_items, n_rep)[0]
            st.session_state["ultimo"] = (df, asis, esc, dict(eco))

    if "ultimo" in st.session_state:
        df, asis, esc, eco_sim = st.session_state["ultimo"]
        st.divider()
        st.subheader(f"Resultado: {esc.nombre} · {len(df)} réplicas")
        m = st.columns(5)
        for col, (k, etiqueta, fmt, ay) in zip(m, [("oee", "OEE de planta", "pct", AYUDA["oee"]),
                                                   ("disponibilidad", "Disponibilidad", "pct", AYUDA["disponibilidad"]),
                                                   ("mtbf_h", "MTBF (h)", "h", AYUDA["mtbf"]),
                                                   ("mttr_h", "MTTR (h)", "h", AYUDA["mttr"]),
                                                   ("paradas_no_planificadas_h", "Paradas (h/año)", "n", AYUDA["paradas"])]):
            v, a = df[k].mean(), asis[k].mean()
            if fmt == "pct":
                col.metric(etiqueta, pct(v), f"{100 * (v - a):+.1f} pp vs AS-IS", help=ay)
            elif fmt == "h":
                col.metric(etiqueta, f"{v:.1f}", f"{v - a:+.1f} vs AS-IS",
                           delta_color="inverse" if k == "mttr_h" else "normal", help=ay)
            else:
                col.metric(etiqueta, f"{v:,.0f}", f"{v - a:+,.0f} vs AS-IS", delta_color="inverse", help=ay)
        panel_comprobacion(comprobar(df, asis, eco_sim), esc.nombre)
        g1, g2 = st.columns(2)
        with g1:
            comp = pd.DataFrame({"AS-IS": [asis.mttr_respuesta_h.mean(), asis.mttr_espera_h.mean(), asis.mttr_reparacion_h.mean()],
                                 "Escenario": [df.mttr_respuesta_h.mean(), df.mttr_espera_h.mean(), df.mttr_reparacion_h.mean()]},
                                index=["Respuesta", "Espera de repuesto", "Reparación"])
            st.markdown("**Componentes del MTTR (h por falla)**")
            st.bar_chart(comp, stack=False, color=[C["claro"], C["iot"]])
        with g2:
            brecha = df.brecha_cerrada.mean()
            st.markdown("**Brecha y actividad IoT**")
            st.progress(min(max(brecha, 0.0), 1.0), text=f"Brecha atribuible a disponibilidad cerrada: {brecha:.0%}")
            st.caption(AYUDA["brecha"])
            if df.alertas_anticipada.mean() > 0:
                st.write(f"Alertas anticipadas: **{df.alertas_anticipada.mean():.1f}** por año · tardías: "
                         f"{df['alertas_tardía'].mean():.1f} · falsas: {df.alertas_falsa.mean():.1f}")
            st.write(f"Horas de técnico: **{df.horas_tecnico.mean():,.0f} h/año** (AS-IS {asis.horas_tecnico.mean():,.0f}).")
            st.caption("Financiable con el presupuesto aprobado y no ejecutado: " + ("sí" if df.financiable.iloc[0] else "no"))
        st.download_button("Descargar resultados (CSV)", df.to_csv(index=False).encode("utf-8"),
                           "resultado_escenario.csv", "text/csv")


def v_comparacion():
    st.title("Comparación y decisión", help="Las 4 combinaciones del diseño factorial 2² (TPM × IoT) con números "
             "aleatorios comunes: todas ven las mismas fallas y lotes.")
    df, _ = factorial_con_aviso(niv_items, eco_items, n_rep, int(p_cal["generales"]["n_tecnicos"]))
    tabla = tabla_comparacion(df)
    r2 = df[df["codigo"] == "AB"]
    asis = df[df["codigo"] == CODIGO_ASIS].sort_values("replica")
    panel_comprobacion(comprobar(r2, asis, eco), "TPM + IoT (R2)")
    mejor, rapido, motivo = recomendar(tabla)
    st.info(f"**Regla de decisión:** {mejor['Escenario']} ({motivo}). Escenario con recuperación más rápida: "
            f"**{rapido['Escenario']}**.")
    orden = tabla.sort_values("OEE (%)")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    colores = [C["tpm"] if c == "AB" else (C["claro"] if c == CODIGO_ASIS else C["iot"]) for c in orden["Código"]]
    ax.barh(orden["Escenario"], orden["OEE (%)"], xerr=orden["± IC 95 %"], color=colores, capsize=3)
    for y, v in enumerate(orden["OEE (%)"]):
        ax.text(v + 0.4, y, f"{v:.1f} %", va="center", fontsize=9)
    ax.axvline(100 * techo, color=C["gris"], ls=":", lw=1.2, label=f"Techo de OEE {100 * techo:.1f} %")
    ax.axvline(85, color=C["bad"], ls="--", lw=1.2, label="Meta 85 %")
    ax.set_xlim(50, 90); ax.set_xlabel("OEE de planta (%)")
    ax.set_title("OEE por escenario (media e IC 95 %)")
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)
    ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    st.pyplot(fig); plt.close(fig)
    st.dataframe(tabla, use_container_width=True, hide_index=True, column_config={
        "OEE (%)": st.column_config.NumberColumn(format="%.1f", help=AYUDA["oee"]),
        "± IC 95 %": st.column_config.NumberColumn(format="%.2f", help="Margen del OEE con 95 % de confianza."),
        "Disponibilidad (%)": st.column_config.NumberColumn(format="%.1f", help=AYUDA["disponibilidad"]),
        "MTBF (h)": st.column_config.NumberColumn(format="%.1f", help=AYUDA["mtbf"]),
        "MTTR (h)": st.column_config.NumberColumn(format="%.2f", help=AYUDA["mttr"]),
        "Paradas no planificadas (h/año)": st.column_config.NumberColumn(format="%.0f", help=AYUDA["paradas"]),
        "Brecha atribuible cerrada (%)": st.column_config.NumberColumn(format="%.1f", help=AYUDA["brecha"]),
        "Inversión inicial (S/)": st.column_config.NumberColumn(format="%.0f"),
        "Costo recurrente (S/ año)": st.column_config.NumberColumn(format="%.0f"),
        "Ahorro operativo (S/ año)": st.column_config.NumberColumn(format="%.0f"),
        "Beneficio neto (S/ año)": st.column_config.NumberColumn(format="%.0f"),
        "Recuperación (meses)": st.column_config.NumberColumn(format="%.1f",
                                                              help="Inversión ÷ (beneficio neto ÷ 12). Vacío o «inf»: no se recupera."),
    })
    st.download_button("Descargar comparación (CSV)", tabla.to_csv(index=False).encode("utf-8"),
                       "comparacion_escenarios.csv", "text/csv")


def v_validacion():
    st.title("Validación del modelo", help="¿El modelo reproduce la planta (validación) y está bien construido "
             "(verificación)? ¿Qué factor explica la mejora y qué tan robusto es el resultado?")
    linea_base = {"OEE (%)": 55.2, "Disponibilidad (%)": 68.6, "MTBF (h)": 20.1, "MTTR (h)": 6.2,
                  "Fallas técnicas": 112, "Paradas no planificadas (h)": 1032.3,
                  "Respuesta mediana (min)": 72.5, "Cumplimiento del preventivo (%)": 38.6}
    kp = corrida_asis(eco_items, n_rep)[0]
    st.subheader("AS-IS simulado frente a la línea base", help="Criterio: error relativo de 5 % o menos en cada indicador. "
                 "Fallas y tiempo de respuesta fueron objetivos de calibración.")
    sim_vals = {"OEE (%)": 100 * kp.oee, "Disponibilidad (%)": 100 * kp.disponibilidad, "MTBF (h)": kp.mtbf_h,
                "MTTR (h)": kp.mttr_h, "Fallas técnicas": kp.fallas,
                "Paradas no planificadas (h)": kp.paradas_no_planificadas_h,
                "Respuesta mediana (min)": kp.respuesta_mediana_min,
                "Cumplimiento del preventivo (%)": 100 * kp.cumplimiento_preventivo}
    filas = []
    for ind, ref in linea_base.items():
        mval, h = intervalo_confianza(sim_vals[ind])
        err = (mval - ref) / ref
        filas.append({"Indicador": ind, "Línea base": ref, "Simulado (media)": mval, "± IC 95 %": h,
                      "Error relativo": err, "Criterio ≤ 5 %": "✅ Cumple" if abs(err) <= 0.05 else "❌ No cumple"})
    st.dataframe(pd.DataFrame(filas).style.format({"Línea base": "{:.1f}", "Simulado (media)": "{:.1f}",
                                                   "± IC 95 %": "{:.2f}", "Error relativo": "{:+.1%}"}),
                 use_container_width=True, hide_index=True)
    with st.expander("Calibración (K2)"):
        st.dataframe(hist_cal.round(3), use_container_width=True, hide_index=True)
    st.subheader("Pruebas de verificación V01–V08", help="Comprueban que el modelo esté bien programado: conservación "
                 "del tiempo, casos extremos y reproducibilidad.")
    if st.button("Ejecutar pruebas V01–V08"):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from pruebas.verificacion import ejecutar_todas
        st.dataframe(ejecutar_todas(p_cal), use_container_width=True, hide_index=True)
    st.subheader("ANOVA del diseño 2² (respuesta: OEE de planta)",
                 help="Efecto de TPM (A), de IoT (B) y de su interacción. p < 0,05 = efecto significativo.")
    df, _ = factorial_con_aviso(niv_items, eco_items, n_rep, int(p_cal["generales"]["n_tecnicos"]))
    an = anova_factorial(df, "oee")
    st.dataframe(an.style.format({"Efecto": "{:+.4f}", "SC": "{:.5f}", "CM": "{:.6f}", "F": "{:.1f}", "p": "{:.4f}"},
                                 na_rep=""), use_container_width=True, hide_index=True)
    medias = df.groupby(["A", "B"])["oee"].mean().unstack()
    fig, ax = plt.subplots(figsize=(5.5, 3.3))
    for b, et, col in ((0, "Sin IoT", C["gris"]), (1, "Con IoT", C["iot"])):
        ax.plot(["Sin TPM", "Con TPM"], 100 * medias[b], marker="o", label=et, color=col)
    ax.set_ylabel("OEE (%)"); ax.set_title("Interacción TPM × IoT")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    st.pyplot(fig); plt.close(fig)
    st.caption("Líneas paralelas = efectos que se suman. Si «Con IoT» se separa más con TPM, hay sinergia.")
    st.subheader("Análisis de sensibilidad de TPM + IoT",
                 help="Mueve cada parámetro incierto a su valor pesimista y optimista, uno a la vez.")
    if st.button("Ejecutar análisis de sensibilidad"):
        with st.spinner("Análisis de sensibilidad… (hasta 1 minuto)"):
            tab, base_oee, _, _ = corrida_sensibilidad(niv_items, eco_items, max(5, n_rep // 2))
        fig, ax = plt.subplots(figsize=(8, 3.6))
        y = np.arange(len(tab))
        ax.barh(y, 100 * (tab["pesimista"] - base_oee), color=C["bad"], label="Pesimista")
        ax.barh(y, 100 * (tab["optimista"] - base_oee), color=C["ok"], label="Optimista")
        ax.set_yticks(y, [NOMBRES_PARAM.get(x, x) for x in tab["parametro"]]); ax.invert_yaxis()
        ax.axvline(0, color="black", lw=0.8); ax.set_xlabel(f"Cambio del OEE (pp) respecto de {pct(base_oee)}")
        ax.set_title("Gráfico de tornado"); ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
        st.pyplot(fig); plt.close(fig)


def boton_libro_actualizado(reg):
    if sesion["ejecuciones"] or sesion["nuevas"]:
        st.download_button(f"⬇ Descargar libro actualizado ({len(sesion['ejecuciones']) + len(sesion['nuevas'])} "
                           "registros nuevos)", libro_actualizado(contenido_reg, reg.preventivos),
                           "registros_CBI_actualizado.xlsx", type="primary",
                           help="Libro Excel con las órdenes registradas en esta sesión. Súbalo luego como «Excel de "
                                "CBI»: la aplicación no guarda cambios en el servidor.")


def guia_sensores(reg=None):
    st.markdown("Cada máquina crítica lleva un kit de **tres sensores**. Sus lecturas permiten ver cómo se "
                "degrada el equipo **antes** de que falle (curva P-F): ese margen es el que TPM usa para programar "
                "la intervención.")
    tarjetas = '<div class="cbi-grid">'
    for info in SENSORES_INFO.values():
        tarjetas += (f'<div class="cbi-card" style="border-top:3px solid {info["color"]}">'
                     f'<h4>{ICONO["sensor"]}{info["titulo"]} <span class="cbi-badge b-gris">{info["unidad"]}</span></h4>'
                     f'<div class="cbi-row"><span><b>Qué mide</b></span></div><div class="sub">{info["mide"]}</div>'
                     f'<div class="cbi-row"><span><b>Dónde se instala</b></span></div><div class="sub">{info["donde"]}</div>'
                     f'<div class="cbi-row"><span><b>Qué falla anticipa</b></span></div><div class="sub">{info["detecta"]}</div>'
                     f'<div class="cbi-row"><span><b>Qué revisar si sale del límite</b></span></div>'
                     f'<div class="sub">{info["revisar"]}</div></div>')
    st.markdown(tarjetas + "</div>", unsafe_allow_html=True)
    st.caption("Límites de alerta: son referenciales y los define CBI con el proveedor de sensores. Para vibración, "
               "las zonas de severidad de ISO 10816-3 (hoy ISO 20816-3) dependen de la potencia de la máquina y del "
               "tipo de base. En el ejemplo sintético se registra una lectura cada 2 horas de turno.")
    if reg is not None and reg.tiene_iot:
        st.markdown("**Sensores registrados**")
        st.dataframe(reg.sensores.rename(columns={"sensor_id": "Sensor", "codigo_equipo": "Equipo", "variable": "Variable",
                                                  "unidad": "Unidad", "limite_alerta": "Límite de alerta"}),
                     hide_index=True, use_container_width=True)


def validacion_tpm(reg):
    st.markdown("**¿Cómo se valida TPM?** Se comparan los indicadores registrados después de implementar TPM con "
                "(1) la **línea base** del diagnóstico y (2) lo que el **modelo** predijo para TPM + IoT. "
                "TPM se considera validado si todos los indicadores mejoran frente a la línea base y alcanzan, con "
                "un margen de 5 %, el valor esperado.")
    if reg.sintetico:
        banner("Con el ejemplo sintético esta tabla solo demuestra el procedimiento: los datos salen del mismo "
               "modelo. La validación real se hace con los registros de CBI.", "sint")
    k, _ = kpi_desde_registros(reg.eventos, reg.lotes, p_cal["lineas"])
    df, _ = factorial_con_aviso(niv_items, eco_items, n_rep, int(p_cal["generales"]["n_tecnicos"]))
    esp = df[df["codigo"] == "AB"].mean(numeric_only=True)
    h_periodo = float(reg.calendario.a_horas([reg.fecha_corte])[0])
    factor = float(p_cal["generales"]["horizonte_h"]) / h_periodo if h_periodo > 0 else 1.0
    pv = reg.preventivos
    clase_a = set(reg.equipos.loc[reg.equipos["clase_a"] == 1, "codigo"])
    plan = pv[(pv["origen"] == "Plan preventivo") & pv["codigo_equipo"].isin(clase_a)] if reg.tiene_tpm else pv
    hechas = int((plan["estado"] == "Realizada").sum()) if len(plan) else 0
    venc = int((plan["estado"] == "Vencida").sum()) if len(plan) else 0
    cumpl = hechas / (hechas + venc) if hechas + venc else float("nan")
    filas = [  # indicador, base, registrado, esperado, mayor es mejor, decimales
        ("Cumplimiento del plan preventivo, clase A (%)", 38.6, 100 * cumpl,
         100 * niv_base["cumplimiento_preventivo_tobe"], True, 1),
        ("MTBF de planta (h)", 20.1, k["mtbf_h"], esp["mtbf_h"], True, 1),
        ("MTTR de planta (h)", 6.2, k["mttr_h"], esp["mttr_h"], False, 2),
        ("Disponibilidad (%)", 68.6, 100 * k["disponibilidad"], 100 * esp["disponibilidad"], True, 1),
        ("Paradas no planificadas (h/año, anualizadas)", 1032.3, k["paradas_no_planificadas_h"] * factor,
         esp["paradas_no_planificadas_h"], False, 0),
        ("OEE de planta (%)", 55.2, 100 * k["oee"], 100 * esp["oee"], True, 1),
    ]
    t = []
    for ind, base, reg_v, esp_v, mayor, d in filas:
        if reg_v is None or (isinstance(reg_v, float) and (math.isnan(reg_v) or math.isinf(reg_v))):
            t.append({"Indicador": ind, "Línea base": round(base, d), "Registrado": None,
                      "Esperado (modelo)": round(esp_v, d), "¿Mejora vs. línea base?": "— Sin datos",
                      "¿Alcanza lo esperado?": "— Sin datos"})
            continue
        mejora = reg_v > base if mayor else reg_v < base
        alcanza = reg_v >= 0.95 * esp_v if mayor else reg_v <= 1.05 * esp_v
        t.append({"Indicador": ind, "Línea base": round(base, d), "Registrado": round(reg_v, d),
                  "Esperado (modelo)": round(esp_v, d), "¿Mejora vs. línea base?": "✅ Sí" if mejora else "❌ No",
                  "¿Alcanza lo esperado?": "✅ Sí" if alcanza else "⚠️ No"})
    t = pd.DataFrame(t)
    st.dataframe(t, hide_index=True, use_container_width=True, column_config={
        "Línea base": st.column_config.NumberColumn(help="Diagnóstico del Capítulo III (antes de TPM)."),
        "Registrado": st.column_config.NumberColumn(help="Calculado con el libro Excel cargado."),
        "Esperado (modelo)": st.column_config.NumberColumn(help="Media del escenario TPM + IoT en el simulador "
                                                                "(nivel de parámetros elegido)."),
    })
    ok_mejora = (t["¿Mejora vs. línea base?"] == "✅ Sí").all()
    ok_alcanza = (t["¿Alcanza lo esperado?"] == "✅ Sí").all()
    if ok_mejora and ok_alcanza:
        st.success("TPM validado: todos los indicadores mejoran frente a la línea base y alcanzan lo esperado.")
    elif ok_mejora:
        st.warning("Los indicadores mejoran frente a la línea base, pero no todos alcanzan lo que predijo el modelo: "
                   "revise el cumplimiento del plan y los parámetros de mejora.")
    else:
        st.error("No todos los indicadores mejoran frente a la línea base: TPM aún no se puede dar por validado.")
    an = anova_factorial(df, "oee").set_index("Fuente")
    p_a = an.loc["A (TPM)", "p"]
    p_txt = "p < 0.001" if p_a < 0.001 else f"p = {p_a:.3f}"
    st.markdown(f"**En el modelo:** el efecto de TPM sobre el OEE es de **{100 * an.loc['A (TPM)', 'Efecto']:+.1f} pp** "
                f"(ANOVA 2², {p_txt}, {n_rep} réplicas).")
    with st.expander("Procedimiento de validación paso a paso"):
        st.markdown("1. **Línea base:** indicadores del diagnóstico antes de TPM (OEE 55,2 %, MTBF 20,1 h, MTTR 6,2 h, "
                    "cumplimiento del preventivo 38,6 %).\n"
                    "2. **Registro:** CBI registra paradas, lotes y órdenes en el libro Excel durante la implementación.\n"
                    "3. **Cálculo:** la aplicación calcula los mismos indicadores (ISO 22400-2 y EN 15341).\n"
                    "4. **Contraste:** cada indicador debe mejorar frente a la línea base y acercarse a lo que predijo "
                    "el modelo.\n"
                    "5. **Causalidad (modelo):** el ANOVA del diseño 2² confirma que el efecto de TPM es significativo.")


def v_mis_ordenes():
    requiere_registros()
    reg = registros
    st.title("Mis órdenes de trabajo", help="Órdenes de mantenimiento que debe ejecutar: próximas y vencidas. "
             "Marque las realizadas y regístrelas.")
    aviso_fuente(reg)
    if not reg.tiene_tpm:
        st.info("No hay órdenes en la hoja «Preventivos».")
        return
    pv = reg.preventivos
    hoy = pd.Timestamp(reg.fecha_corte)
    abiertas = pv[pv["estado"] != "Realizada"]
    venc = abiertas[abiertas["estado"] == "Vencida"].sort_values("fecha_programada")
    prox = abiertas[(abiertas["fecha_programada"] > hoy) &
                    (abiertas["fecha_programada"] <= hoy + pd.Timedelta(days=7))].sort_values("fecha_programada")
    m = st.columns(3)
    m[0].metric("Próximos 7 días", len(prox), help="Órdenes programadas en la próxima semana.")
    m[1].metric("Vencidas", len(venc), help=AYUDA["vencidas"])
    m[2].metric("Registradas en esta sesión", len(sesion["ejecuciones"]))
    st.caption(f"«Hoy» corresponde a la fecha de corte de los registros: {hoy:%d/%m/%Y}.")
    for titulo, datos, clave in (("Próximos 7 días", prox, "prox"), ("Vencidas", venc, "venc")):
        st.subheader(f"{titulo} ({len(datos)})")
        if datos.empty:
            st.caption("Nada en esta lista.")
            continue
        editable = pd.DataFrame({
            "Hecha": [False] * len(datos), "OT": datos["id_orden"].values, "Equipo": datos["codigo_equipo"].values,
            "Actividad": datos["actividad"].values, "Origen": datos["origen"].values,
            "Programada": datos["fecha_programada"].values,
            "Fecha de ejecución": [hoy.date()] * len(datos), "Observación": [""] * len(datos)})
        res = st.data_editor(editable, hide_index=True, use_container_width=True, key=f"editor_{clave}",
                             disabled=["OT", "Equipo", "Actividad", "Origen", "Programada"],
                             column_config={
                                 "Hecha": st.column_config.CheckboxColumn(help="Marque la orden si la ejecutó."),
                                 "Programada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                                 "Fecha de ejecución": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                 "Observación": st.column_config.TextColumn(help="Qué encontró o qué cambió.")})
        if st.button(f"Registrar órdenes marcadas · {titulo.lower()}", key=f"guardar_{clave}"):
            marcadas = res[res["Hecha"]]
            if marcadas.empty:
                st.warning("Marque al menos una orden en la columna «Hecha».")
            elif not tecnico:
                st.warning("Escriba su nombre en la barra lateral antes de registrar.")
            else:
                for _, r in marcadas.iterrows():
                    sesion["ejecuciones"][r["OT"]] = dict(fecha=r["Fecha de ejecución"], obs=r["Observación"],
                                                          por=tecnico)
                st.success(f"{len(marcadas)} órdenes registradas.")
                st.rerun()
    boton_libro_actualizado(reg)


def v_checklist():
    requiere_registros()
    reg = registros
    st.title("Checklist de mantenimiento autónomo", help="Inspección diaria de 15 minutos en los equipos críticos "
             "(pilar de mantenimiento autónomo de TPM).")
    aviso_fuente(reg)
    criticos = list(reg.equipos.loc[reg.equipos["clase_a"] == 1, "codigo"]) or list(reg.equipos["codigo"])
    items = ["Limpieza del equipo y su entorno", "Inspección visual: fugas, ruidos y fijaciones",
             "Lubricación de los puntos indicados", "Ajuste y apriete de elementos sueltos",
             "Revisión de guardas y dispositivos de seguridad"]
    with st.form("checklist", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        cod = c1.selectbox("Equipo", criticos, format_func=lambda c: f"{c} · {nombre_eq.get(c, '')}")
        fecha = c2.date_input("Fecha", value=pd.Timestamp(reg.fecha_corte).date(), format="DD/MM/YYYY")
        marcados = [st.checkbox(i) for i in items]
        anomalia = st.text_area("Anomalía detectada (opcional)", placeholder="Ej.: ruido en el rodamiento del agitador",
                                help="Si describe una anomalía, se crea una orden de trabajo pendiente para mantenimiento.")
        enviado = st.form_submit_button("Registrar checklist", type="primary")
    if enviado:
        if not tecnico:
            st.warning("Escriba su nombre en la barra lateral antes de registrar.")
        else:
            hora = float(reg.config.get("hora_inicio_turno", 7.0))
            n = len(sesion["nuevas"]) + 1
            faltan = [i for i, ok in zip(items, marcados) if not ok]
            base = dict(codigo_equipo=cod, origen="Mantenimiento autónomo", id_alerta="", responsable=tecnico,
                        fin_ejecucion=pd.NaT)
            inicio = pd.Timestamp(fecha) + pd.Timedelta(hours=hora)
            sesion["nuevas"].append(dict(base, id_orden=f"MA-{n:03d}",
                                         actividad=f"Checklist autónomo ({sum(marcados)}/{len(items)} ítems)",
                                         fecha_programada=inicio, inicio_ejecucion=inicio, ejecutado_por=tecnico,
                                         observacion=("Pendiente: " + "; ".join(faltan)) if faltan else "Completo",
                                         estado="Realizada"))
            if anomalia.strip():
                sesion["nuevas"].append(dict(base, id_orden=f"MA-{n:03d}-A", actividad=f"Anomalía: {anomalia.strip()}",
                                             fecha_programada=inicio + pd.Timedelta(days=1), inicio_ejecucion=pd.NaT,
                                             ejecutado_por="", observacion="Reportada en el checklist",
                                             estado="Pendiente"))
            st.success("Checklist registrado" + (" y orden de trabajo creada por la anomalía." if anomalia.strip() else "."))
            st.rerun()
    hechos = [r for r in sesion["nuevas"] if r["origen"] == "Mantenimiento autónomo"]
    if hechos:
        st.subheader("Registrados en esta sesión")
        st.dataframe(pd.DataFrame(hechos)[["id_orden", "codigo_equipo", "actividad", "fecha_programada", "estado",
                                           "observacion"]], hide_index=True, use_container_width=True,
                     column_config={"fecha_programada": st.column_config.DatetimeColumn("Fecha", format="DD/MM/YYYY")})
        boton_libro_actualizado(reg)


def v_alertas_tecnico():
    requiere_registros()
    reg = registros
    st.title("Alertas de las máquinas", help="Máquinas cuyo sensor está fuera de límite o que tuvieron alertas en la "
             "última semana, con qué revisar y la orden de trabajo relacionada.")
    aviso_fuente(reg)
    if not reg.tiene_iot:
        st.info("No hay sensores registrados.")
        return
    es = estado_sensores(reg.sensores, reg.lecturas, reg.fecha_corte)
    hoy = pd.Timestamp(reg.fecha_corte)
    al = reg.alertas[reg.alertas["fecha_hora"] >= hoy - pd.Timedelta(days=7)] if not reg.alertas.empty else pd.DataFrame()
    fuera = es[es["condicion"] == "Fuera de límite"]
    sin_datos = es[es["transmision"] != "Transmitiendo"]
    m = st.columns(3)
    m[0].metric("Sensores fuera de límite", len(fuera), help=AYUDA["condicion"])
    m[1].metric("Alertas de la última semana", len(al), help=AYUDA["alertas"])
    m[2].metric("Sensores sin datos recientes", len(sin_datos), help=AYUDA["transmision"])
    if fuera.empty and al.empty:
        st.success("Sin alertas en la última semana: todas las lecturas están dentro de su límite.")
    if not fuera.empty:
        tarjetas = '<div class="cbi-grid">'
        for r in fuera.itertuples():
            inf = info_variable(r.variable) or {}
            tarjetas += (f'<div class="cbi-card" style="border-top:3px solid {C["bad"]}"><h4>{ICONO["sensor"]}'
                         f'{html.escape(r.codigo_equipo)} {badge("Fuera de límite", "b-bad")}</h4>'
                         f'<div class="sub">{html.escape(nombre_eq.get(r.codigo_equipo, ""))}</div>'
                         f'<div class="cbi-row"><span>{html.escape(str(r.variable))}</span><span class="v">'
                         f'{r.ultimo_valor:g} / {r.limite_alerta:g} {html.escape(str(r.unidad))}</span></div>'
                         f'<div class="sub" style="margin-top:6px"><b>Qué revisar:</b> '
                         f'{inf.get("revisar", "Revisar el equipo.")}</div></div>')
        st.markdown(tarjetas + "</div>", unsafe_allow_html=True)
    if not al.empty:
        st.subheader("Alertas de la última semana")
        pv = reg.preventivos if reg.tiene_tpm else pd.DataFrame(columns=["id_alerta", "id_orden", "estado"])
        t = al.merge(pv[["id_alerta", "id_orden", "estado"]], on="id_alerta", how="left") \
            .sort_values("fecha_hora", ascending=False)
        var = t["sensor_id"].map(dict(zip(reg.sensores["sensor_id"], reg.sensores["variable"]))).fillna("")
        t["Qué revisar"] = [(info_variable(v) or {}).get("revisar", "") for v in var]
        st.dataframe(t[["fecha_hora", "codigo_equipo", "sensor_id", "tipo", "id_orden", "estado", "Qué revisar"]].rename(
            columns={"fecha_hora": "Fecha", "codigo_equipo": "Equipo", "sensor_id": "Sensor", "tipo": "Tipo",
                     "id_orden": "OT", "estado": "Estado OT"}), hide_index=True, use_container_width=True,
            column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})


def v_guia_sensores():
    st.title("¿Qué miden los sensores?", help="Guía rápida de las variables que monitorea IoT y qué hacer cuando "
             "una lectura sale de su límite.")
    guia_sensores(registros)


DESPACHO = {
    "Inicio · ¿Cómo funciona?": v_inicio,
    "IoT · Monitoreo de máquinas": v_iot,
    "TPM · Gestión del mantenimiento": v_tpm,
    "Ficha de máquina · IoT + TPM": v_ficha,
    "Indicadores desde registros": v_indicadores,
    "Situación actual (AS-IS)": v_asis,
    "Simulador de escenarios": v_simulador,
    "Comparación y decisión": v_comparacion,
    "Validación del modelo": v_validacion,
    "Mis órdenes de trabajo": v_mis_ordenes,
    "Checklist de mantenimiento autónomo": v_checklist,
    "Alertas de las máquinas": v_alertas_tecnico,
    "¿Qué miden los sensores?": v_guia_sensores,
}
DESPACHO[vista]()
print(f"SimTI: pantalla mostrada ({vista})", flush=True)
