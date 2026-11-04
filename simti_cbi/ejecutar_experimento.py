"""Corre el experimento completo sin interfaz y guarda tablas y figuras.

Ejecutar:  python ejecutar_experimento.py [réplicas]
Salidas en la carpeta resultados/.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simti.datos import cargar_parametros, niveles_escenario
from simti.ajuste import calibrar
from simti.escenarios import diseno_factorial, CODIGO_ASIS
from simti.experimento import correr, correr_sensibilidad
from simti.kpi import anova_factorial, intervalo_confianza, replicas_necesarias, techo_planta
from simti.decision import tabla_comparacion, recomendar
from pruebas.verificacion import ejecutar_todas

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
OUT = Path(__file__).parent / "resultados"
OUT.mkdir(exist_ok=True)

p, hist = calibrar(cargar_parametros())
hist.to_csv(OUT / "calibracion.csv", index=False)
niv = niveles_escenario(p, "base")
techo = techo_planta(p["lineas"])

ver = ejecutar_todas(p)
ver.to_csv(OUT / "verificacion.csv", index=False)
print(ver[["ID", "Resultado"]].to_string(index=False))

df, dl = correr(p, diseno_factorial(niv), N)
df.to_csv(OUT / "factorial_replicas.csv", index=False)
dl.to_csv(OUT / "factorial_lineas.csv", index=False)

asis = df[df.codigo == CODIGO_ASIS]
ref = {"oee": 0.552, "disponibilidad": 0.686, "mtbf_h": 20.1, "mttr_h": 6.2, "fallas": 112,
       "paradas_no_planificadas_h": 1032.3, "respuesta_mediana_min": 72.5,
       "cumplimiento_preventivo": 0.386}
val = []
for k, r in ref.items():
    m, h = intervalo_confianza(asis[k])
    val.append(dict(indicador=k, linea_base=r, simulado=m, ic95=h, error_rel=(m - r) / r))
val = pd.DataFrame(val)
val.to_csv(OUT / "validacion_asis.csv", index=False)
print(val.round(4).to_string(index=False))
print("Réplicas necesarias para IC ±1 pp de OEE:", replicas_necesarias(asis.oee, 0.01))

tabla = tabla_comparacion(df)
tabla.to_csv(OUT / "comparacion_escenarios.csv", index=False)
mejor, rapido, motivo = recomendar(tabla)
print(tabla.round(2).to_string(index=False))
print("Recomendado:", mejor["Escenario"], "|", motivo, "| más rápido:", rapido["Escenario"])

an = anova_factorial(df, "oee")
an.to_csv(OUT / "anova_oee.csv", index=False)
print(an.round(5).to_string(index=False))
an_d = anova_factorial(df, "disponibilidad")
an_d.to_csv(OUT / "anova_disponibilidad.csv", index=False)

cols = ["mttr_respuesta_h", "mttr_espera_h", "mttr_reparacion_h", "fallas", "alertas_anticipada",
        "alertas_tardía", "alertas_falsa", "horas_tecnico", "lotes_retrasados", "lead_time_medio_h",
        "cumplimiento_preventivo", "ahorro_operativo", "costo_recurrente"]
det = df.groupby("escenario", sort=False)[cols].mean()
det.to_csv(OUT / "detalle_escenarios.csv")
print(det.round(2).to_string())

lin = dl.groupby(["escenario", "linea"], sort=False)[["oee", "disponibilidad", "techo_oee"]].mean().reset_index()
lin.to_csv(OUT / "oee_por_linea.csv", index=False)

sens, base_oee, base_neto, sens_largo = correr_sensibilidad(p, niv, max(10, N // 3))
sens.to_csv(OUT / "sensibilidad_oee.csv", index=False)
sens_largo.to_csv(OUT / "sensibilidad_detalle.csv", index=False)
print("Sensibilidad (base OEE %.4f, neto %.0f)" % (base_oee, base_neto))
print(sens.round(4).to_string(index=False))

# ---------------------------------------------------------------- figuras
plt.rcParams.update({"font.size": 10})
orden = tabla.sort_values("OEE (%)")
fig, ax = plt.subplots(figsize=(9, 4.4))
ax.barh(orden["Escenario"], orden["OEE (%)"], xerr=orden["± IC 95 %"], color="#2f6f9f", capsize=3)
for y, v in enumerate(orden["OEE (%)"]):
    ax.text(v + 0.6, y, f"{v:.1f} %", va="center", fontsize=9)
ax.axvline(100 * techo, color="#7f8c8d", ls=":", lw=1.2, label=f"Techo de OEE {100 * techo:.1f} %")
ax.axvline(85, color="#c0392b", ls="--", lw=1.2, label="Meta 85 %")
ax.set_xlim(45, 90); ax.set_xlabel("OEE de planta (%)")
ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
fig.savefig(OUT / "fig_oee_escenarios.png", dpi=200)

medias = df.groupby(["A", "B"])["oee"].mean().unstack()
fig, ax = plt.subplots(figsize=(5.5, 3.6))
for b, et, c in ((0, "Sin IoT", "#7f8c8d"), (1, "Con IoT", "#2f6f9f")):
    ax.plot(["Sin TPM", "Con TPM"], 100 * medias[b], marker="o", label=et, color=c)
ax.set_ylabel("OEE de planta (%)"); ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
fig.savefig(OUT / "fig_interaccion_tpm_iot.png", dpi=200)

nombres = {"delta_tpm_mtbf": "Mejora del MTBF por TPM", "red_reparacion_tpm": "Reducción de la reparación (TPM)",
           "p_deteccion": "Probabilidad de detección IoT",
           "frac_anticipada": "Alertas anticipadas", "red_respuesta_alerta": "Reducción de respuesta con alerta",
           "falsas_alarmas_mes": "Falsas alarmas por mes", "n_tecnicos": "Número de técnicos (1 → 2)"}
fig, ax = plt.subplots(figsize=(8, 4))
y = np.arange(len(sens))
ax.barh(y, 100 * (sens["pesimista"] - base_oee), color="#c0392b", label="Nivel pesimista")
ax.barh(y, 100 * (sens["optimista"] - base_oee), color="#27ae60", label="Nivel optimista")
ax.set_yticks(y, [nombres.get(x, x) for x in sens["parametro"]]); ax.invert_yaxis()
ax.axvline(0, color="black", lw=0.8); ax.set_xlabel(f"Cambio del OEE (pp) respecto de {100 * base_oee:.1f} %")
ax.legend(frameon=False, loc="lower right"); ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
fig.savefig(OUT / "fig_tornado.png", dpi=200)

comp = df.groupby("escenario", sort=False)[["mttr_respuesta_h", "mttr_espera_h", "mttr_reparacion_h"]].mean()
fig, ax = plt.subplots(figsize=(9, 4.2))
izq = np.zeros(len(comp))
for col, et, c in (("mttr_respuesta_h", "Respuesta", "#95a5a6"), ("mttr_espera_h", "Espera de repuesto", "#c0392b"),
                   ("mttr_reparacion_h", "Reparación activa", "#2f6f9f")):
    ax.barh(comp.index, comp[col], left=izq, label=et, color=c); izq += comp[col].to_numpy()
ax.invert_yaxis(); ax.set_xlabel("Horas por falla")
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
fig.savefig(OUT / "fig_mttr_componentes.png", dpi=200)
print("Listo:", OUT)
