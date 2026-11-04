"""Genera los libros Excel de registros de planta.

    plantilla_registros_CBI.xlsx   libro vacío para que CBI Perú cargue sus datos reales
    ejemplo_sintetico_CBI.xlsx     libro con DATOS SINTÉTICOS para probar la herramienta

Los datos sintéticos salen de una corrida del simulador calibrado (escenario TPM + IoT,
nivel base, semilla 2026) ubicada en 2024. Las lecturas de sensores son señales sintéticas
construidas para ser coherentes con las alertas simuladas; no provienen de sensores físicos.

Ejecutar desde la carpeta del proyecto:  python datos/generar_excel.py
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from simti.ajuste import calibrar
from simti.datos import CARPETA_DATOS, cargar_parametros, niveles_escenario
from simti.escenarios import NOMBRES, Escenario
from simti.motor import simular
from simti.registros import COLUMNAS, Calendario

INICIO = date(2024, 1, 2)
CORTE = datetime(2024, 10, 31, 15, 0)
SEMILLA = 2026
VARIABLES = [  # sensor, variable, unidad, valor base, desviación, límite referencial
    ("VIB", "Vibración (RMS)", "mm/s", 2.0, 0.25, 4.5),
    ("TMP", "Temperatura", "°C", 52.0, 1.5, 70.0),
    ("COR", "Corriente", "A", 20.0, 0.8, 28.0),
]
RESULTADO_ALERTA = {"anticipada": "OT programada (sin parada)",
                    "tardía": "Falla con atención más rápida",
                    "falsa": "Falsa alarma (inspección sin hallazgo)"}

DICCIONARIO = [
    ("Configuracion", "inicio_periodo", "Primer día del periodo registrado", "02/01/2024"),
    ("Configuracion", "hora_inicio_turno", "Hora de inicio del turno", "07:00"),
    ("Configuracion", "horas_por_turno", "Horas del turno", "8"),
    ("Configuracion", "dias_laborables", "Días de trabajo", "lun-sab"),
    ("Configuracion", "fecha_corte", "Fecha hasta la que hay registros (vacío = la última registrada)", "31/10/2024"),
    ("Configuracion", "naturaleza_datos", "Real o Sintético", "Real (CBI Perú)"),
    ("Equipos", "codigo", "Código del equipo (igual en todas las hojas)", "Rx-L1-03"),
    ("Equipos", "clase_a / sensor_iot", "Sí o No", "Sí"),
    ("Paradas", "tipo", "falla_tecnica, no_tecnica u ot_programada", "falla_tecnica"),
    ("Paradas", "categoria", "Causa de la parada", "Mecánica/lubricación"),
    ("Paradas", "inicio_parada", "Fecha y hora en que el equipo se detuvo", "15/03/2024 09:20"),
    ("Paradas", "inicio_atencion", "Fecha y hora en que llegó el técnico", "15/03/2024 10:35"),
    ("Paradas", "espera_repuesto_h", "Horas esperando repuesto o proveedor (0 si no hubo)", "2,5"),
    ("Paradas", "fin_parada", "Fecha y hora en que el equipo volvió a operar", "15/03/2024 14:10"),
    ("Paradas", "id_alerta", "Alerta IoT relacionada, si la hubo", "AL-0012"),
    ("Lotes", "marcha_std_h / marcha_h / paradas_h", "Horas estándar, horas reales de marcha y horas de parada del lote", "1,2 / 1,2 / 0"),
    ("Preventivos", "origen", "Plan preventivo, Alerta IoT o Mantenimiento autónomo", "Plan preventivo"),
    ("Preventivos", "fecha_programada / inicio_ejecucion / fin_ejecucion", "Vacío en ejecución = aún no realizada", "05/02/2024 08:00"),
    ("Preventivos", "ejecutado_por / observacion", "Quién ejecutó la orden y qué encontró (lo llena el técnico)", "J. Pérez · rodamiento con ruido"),
    ("Sensores", "limite_alerta", "Valor a partir del cual la lectura se considera anormal (definir con el proveedor)", "4,5"),
    ("Lecturas_IoT", "fecha_hora / sensor_id / valor", "Una fila por lectura exportada de la plataforma IoT", "15/03/2024 09:00 · Rx-L1-03-VIB · 2,1"),
    ("Alertas_IoT", "tipo", "anticipada, tardía o falsa", "anticipada"),
]


def _redondear(dt):
    return pd.Timestamp(dt).round("min").to_pydatetime()


def _equipos(p):
    eq = p["equipos"]
    return pd.DataFrame({"codigo": eq["codigo"], "descripcion": eq["descripcion"], "linea": eq["linea"],
                         "clase_a": np.where(eq["clase_a"] == 1, "Sí", "No"),
                         "sensor_iot": np.where(eq["sensor_candidato"] == 1, "Sí", "No")})


def _sensores(p, con_limite=True):
    filas = []
    for cod in p["equipos"].loc[p["equipos"]["sensor_candidato"] == 1, "codigo"]:
        for sid, var, uni, _, _, lim in VARIABLES:
            filas.append(dict(sensor_id=f"{cod}-{sid}", codigo_equipo=cod, variable=var, unidad=uni,
                              limite_alerta=lim if con_limite else None))
    return pd.DataFrame(filas, columns=COLUMNAS["Sensores"])


def _config(naturaleza, inicio=None, corte=None):
    return pd.DataFrame([
        ("inicio_periodo", inicio, "Primer día del periodo (vacío = la fecha más antigua registrada)"),
        ("hora_inicio_turno", "07:00", "Hora de inicio del turno"),
        ("horas_por_turno", 8, "Horas que dura el turno"),
        ("dias_laborables", "lun-sab", "Días de trabajo (ej.: lun-sab o lun,mar,mie,jue,vie)"),
        ("fecha_corte", corte, "Último día con registros (vacío = el último registrado)"),
        ("naturaleza_datos", naturaleza, "Real o Sintético: la aplicación lo muestra en pantalla"),
    ], columns=["parametro", "valor", "descripcion"])


def _leeme(sintetico):
    t = ["SimTI-CBI · R2 TPM + IoT — Libro de registros de planta", ""]
    if sintetico:
        t += ["⚠ DATOS SINTÉTICOS. Este libro fue generado con el simulador (escenario TPM + IoT, 2024).",
              "Sirve solo para probar la herramienta. No son datos de CBI Perú ni de sensores físicos.", ""]
    t += ["Cómo usarlo:",
          "1. Complete Configuracion (calendario de turnos) y revise la hoja Equipos.",
          "2. Obligatorias: Paradas y Lotes (con ellas se calculan OEE, disponibilidad, MTBF y MTTR).",
          "3. Opcionales: Preventivos (sección TPM), Sensores, Lecturas_IoT y Alertas_IoT (sección IoT).",
          "4. No cambie los nombres de las hojas ni de las columnas (fila 1). Una fila por registro.",
          "5. Fechas en formato dd/mm/aaaa hh:mm. Horas con decimales (ej.: 2,5).",
          "6. Suba el archivo en la aplicación: barra lateral → Fuente de datos → Excel de CBI.",
          "", "Diccionario de columnas principales:"]
    return t


def _escribir(ruta, hojas, sintetico):
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        pd.DataFrame({"LEEME": _leeme(sintetico)}).to_excel(w, sheet_name="LEEME", index=False, header=False)
        dic = pd.DataFrame(DICCIONARIO, columns=["Hoja", "Columna", "Descripción", "Ejemplo"])
        dic.to_excel(w, sheet_name="LEEME", index=False, startrow=len(_leeme(sintetico)) + 1)
        for nombre, df in hojas.items():
            df.to_excel(w, sheet_name=nombre, index=False)
    wb = load_workbook(ruta)
    cab = PatternFill("solid", fgColor="1E293B")
    for ws in wb.worksheets:
        if ws.title == "LEEME":
            ws.column_dimensions["A"].width = 26
            ws.column_dimensions["B"].width = 40
            ws.column_dimensions["C"].width = 70
            ws.column_dimensions["D"].width = 34
            ws["A1"].font = Font(bold=True, size=14)
            if sintetico:
                for fila in (3, 4):
                    ws.cell(fila, 1).font = Font(bold=True, color="B45309")
                ws.sheet_properties.tabColor = "D97706"
            r0 = len(_leeme(sintetico)) + 2
            for c in ws[r0]:
                c.font, c.fill = Font(bold=True, color="FFFFFF"), cab
            continue
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), cab
            c.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"
        for j, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 200)), start=1):
            ancho = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[get_column_letter(j)].width = min(max(12, ancho + 2), 48)
            for c in col[1:]:
                if isinstance(c.value, datetime):
                    c.number_format = "dd/mm/yyyy hh:mm"
        if sintetico:
            ws.sheet_properties.tabColor = "D97706"
        validaciones = {"Paradas": {"tipo": "falla_tecnica,no_tecnica,ot_programada"},
                        "Preventivos": {"origen": "Plan preventivo,Alerta IoT,Mantenimiento autónomo"},
                        "Alertas_IoT": {"tipo": "anticipada,tardía,falsa"},
                        "Equipos": {"clase_a": "Sí,No", "sensor_iot": "Sí,No"}}.get(ws.title, {})
        cabeceras = [c.value for c in ws[1]]
        for col, lista in validaciones.items():
            if col in cabeceras:
                letra = get_column_letter(cabeceras.index(col) + 1)
                dv = DataValidation(type="list", formula1=f'"{lista}"', allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(f"{letra}2:{letra}5000")
    wb.save(ruta)


def plantilla(p, ruta):
    hojas = {"Configuracion": _config("Real (CBI Perú)"), "Equipos": _equipos(p)}
    for h in ("Paradas", "Lotes", "Preventivos"):
        hojas[h] = pd.DataFrame(columns=COLUMNAS[h])
    hojas["Sensores"] = _sensores(p, con_limite=False)
    for h in ("Lecturas_IoT", "Alertas_IoT"):
        hojas[h] = pd.DataFrame(columns=COLUMNAS[h])
    _escribir(ruta, hojas, sintetico=False)


def ejemplo_sintetico(p, ruta):
    cal = Calendario(INICIO, 7.0, 8.0, "lun-sab")
    hc = float(cal.a_horas([CORTE])[0])
    niv = niveles_escenario(p)
    sim = simular(p, Escenario(NOMBRES[(True, True)], True, True, niv, 1), SEMILLA)
    rng = np.random.default_rng(SEMILLA)
    f = lambda h, fin=False: _redondear(cal.a_fecha(h, es_fin=fin))

    ev = pd.DataFrame(sim.eventos)
    fallas = ev[ev["tipo"].isin(["falla_tecnica", "no_tecnica"]) & (ev["fin_parada_h"] <= hc)]
    paradas = pd.DataFrame({
        "id_evento": [f"EV-{i:04d}" for i in range(1, len(fallas) + 1)],
        "codigo_equipo": fallas["codigo_equipo"].values, "linea": fallas["linea"].values,
        "tipo": fallas["tipo"].values, "categoria": fallas["categoria"].values,
        "inicio_parada": [f(h) for h in fallas["inicio_parada_h"]],
        "inicio_atencion": [f(h) for h in fallas["inicio_atencion_h"]],
        "espera_repuesto_h": fallas["espera_repuesto_h"].round(2).values,
        "fin_parada": [f(h, True) for h in fallas["fin_parada_h"]],
        "id_lote": fallas["id_lote"].values, "id_alerta": fallas["id_alerta"].values})

    lt = pd.DataFrame(sim.lotes)
    lt = lt[lt["fin_h"] <= hc]
    lotes = pd.DataFrame({
        "id_lote": lt["id_lote"], "codigo_equipo": lt["codigo_equipo"], "linea": lt["linea"],
        "llegada": [f(h) for h in lt["llegada_h"]], "inicio": [f(h) for h in lt["inicio_h"]],
        "fin": [f(h, True) for h in lt["fin_h"]], "marcha_std_h": lt["marcha_std_h"].round(3),
        "marcha_h": lt["marcha_h"].round(3), "paradas_h": lt["paradas_h"].round(3)})

    # ---- TPM: plan preventivo y OT originadas por alertas IoT
    codigos = set(p["equipos"]["codigo"])
    pv = pd.DataFrame(sim.preventivos)
    pv = pv[pv["codigo_equipo"].isin(codigos)].sort_values("programado_h")
    filas = []
    for r in pv.itertuples():
        hecho = bool(r.ejecutado) and r.inicio_ejecucion_h is not None and r.inicio_ejecucion_h <= hc
        filas.append(dict(codigo_equipo=r.codigo_equipo,
                          actividad="Preventivo programado (F-MT-06)" + (" · TPM" if r.tpm else ""),
                          origen="Plan preventivo", id_alerta="", fecha_programada=f(r.programado_h),
                          inicio_ejecucion=f(r.inicio_ejecucion_h) if hecho else None,
                          fin_ejecucion=f(r.fin_ejecucion_h, True) if hecho else None,
                          responsable="Técnico de mantenimiento",
                          ejecutado_por="Técnico de mantenimiento" if hecho else "", observacion=""))
    al = pd.DataFrame(sim.alertas)
    ots = ev[ev["tipo"] == "ot_programada"].set_index("id_alerta")
    for r in al[(al["tipo"] == "anticipada") & (al["tiempo_h"] <= hc)].itertuples():
        hecho = r.id_alerta in ots.index and ots.loc[r.id_alerta, "inicio_parada_h"] <= hc
        filas.append(dict(codigo_equipo=r.codigo_equipo, actividad="Intervención por alerta IoT",
                          origen="Alerta IoT", id_alerta=r.id_alerta, fecha_programada=f(r.tiempo_h),
                          inicio_ejecucion=f(ots.loc[r.id_alerta, "inicio_parada_h"]) if hecho else None,
                          fin_ejecucion=f(ots.loc[r.id_alerta, "fin_parada_h"], True) if hecho else None,
                          responsable="Técnico de mantenimiento",
                          ejecutado_por="Técnico de mantenimiento" if hecho else "", observacion=""))
    prev = pd.DataFrame(filas).sort_values("fecha_programada").reset_index(drop=True)
    prev.insert(0, "id_orden", [f"OT-{i:04d}" for i in range(1, len(prev) + 1)])

    # ---- IoT: sensores, alertas y lecturas sintéticas coherentes con las alertas
    sensores = _sensores(p)
    al = al[al["tiempo_h"] <= hc].copy()
    al["sensor_id"] = [f"{c}-" + (rng.choice(["VIB", "TMP"], p=[0.6, 0.4]) if t != "falsa"
                                  else rng.choice(["VIB", "TMP", "COR"]))
                       for c, t in zip(al["codigo_equipo"], al["tipo"])]
    alertas = pd.DataFrame({"id_alerta": al["id_alerta"], "fecha_hora": [f(h) for h in al["tiempo_h"]],
                            "codigo_equipo": al["codigo_equipo"], "sensor_id": al["sensor_id"],
                            "tipo": al["tipo"], "resultado": al["tipo"].map(RESULTADO_ALERTA)})
    fin_falla = ev[ev["tipo"] == "falla_tecnica"]
    malla = np.arange(1.0, hc, 2.0)
    lecturas = []
    for s in sensores.itertuples():
        base, sd, lim = next((b, d, l) for sid, _, _, b, d, l in VARIABLES if s.sensor_id.endswith(sid))
        v = base + rng.normal(0, sd, len(malla))
        for a in al[al["sensor_id"] == s.sensor_id].itertuples():
            if a.tipo == "falsa":
                k = np.searchsorted(malla, a.tiempo_h)
                if k < len(malla):
                    v[k] = lim * 1.15
                continue
            if a.tipo == "anticipada" and a.id_alerta in ots.index:
                fin = float(ots.loc[a.id_alerta, "fin_parada_h"])
            else:
                sig = fin_falla[(fin_falla["codigo_equipo"] == a.codigo_equipo) &
                                (fin_falla["inicio_parada_h"] >= a.tiempo_h - 1e-6)]
                fin = float(sig["fin_parada_h"].iloc[0]) if len(sig) else a.tiempo_h + 8
            fin = min(fin, a.tiempo_h + 24)
            rampa = (malla >= a.tiempo_h - 16) & (malla <= a.tiempo_h)
            v[rampa] = base + (malla[rampa] - (a.tiempo_h - 16)) / 16 * (lim * 1.1 - base) + rng.normal(0, sd, rampa.sum())
            alto = (malla > a.tiempo_h) & (malla <= fin)
            v[alto] = lim * 1.05 + rng.normal(0, sd, alto.sum())
        lecturas.append(pd.DataFrame({"fecha_hora": [f(h) for h in malla], "sensor_id": s.sensor_id,
                                      "valor": np.round(v, 2)}))
    lecturas = pd.concat(lecturas, ignore_index=True)

    hojas = {"Configuracion": _config(f"Sintético (simulador SimTI-CBI, escenario TPM + IoT, semilla {SEMILLA})",
                                      INICIO, CORTE.date()),
             "Equipos": _equipos(p), "Paradas": paradas, "Lotes": lotes, "Preventivos": prev,
             "Sensores": sensores, "Lecturas_IoT": lecturas, "Alertas_IoT": alertas}
    _escribir(ruta, hojas, sintetico=True)
    return {h: len(d) for h, d in hojas.items()}


if __name__ == "__main__":
    p, _ = calibrar(cargar_parametros())
    plantilla(p, CARPETA_DATOS / "plantilla_registros_CBI.xlsx")
    print("Plantilla:", CARPETA_DATOS / "plantilla_registros_CBI.xlsx")
    print("Ejemplo sintético:", ejemplo_sintetico(p, CARPETA_DATOS / "ejemplo_sintetico_CBI.xlsx"))
