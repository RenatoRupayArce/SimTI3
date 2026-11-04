"""K1 · Derivación trazable de los parámetros de entrada del simulador.

Construye los archivos CSV de parámetros a partir de las cifras del diagnóstico
(Capítulo III, Tablas 8 y 10 de la tesis). Cada número indica su origen.
Ejecutar:  python datos/derivar_parametros.py
"""
from pathlib import Path
import csv

AQUI = Path(__file__).parent

# --- Tabla 8: OEE y sus factores por línea (línea base de referencia) ---------
LINEAS = [
    # linea, tiempo planificado (h), disponibilidad, rendimiento, calidad, OEE
    ("Formulación de líquidos", 1223.9, 0.626, 0.832, 0.950, 0.494),
    ("Formulación de sólidos", 1113.0, 0.703, 0.841, 0.984, 0.582),
    ("Molienda de insumos", 499.9, 0.672, 0.771, 0.990, 0.513),
    ("Envasado de líquidos", 270.3, 0.739, 0.778, 0.981, 0.564),
    ("Sellado de bolsas", 177.3, 0.947, 0.919, 0.983, 0.855),
]

# --- Tabla 10: equipos críticos (N.° de fallas, MTBF, MTTR) ------------------
# Los equipos sin dato completo en la Tabla 10 (MH-L3-02, DL-L1-01 y "otros")
# se completan para que los totales de planta cierren: 112 fallas, MTBF 20,1 h,
# MTTR 6,2 h y 1 032,3 h de paradas (ver comprobación al final).
EQUIPOS = [
    # codigo, descripcion, linea, claseA, sensor_candidato, fallas, mtbf, mttr,
    # frac_mec_lub, frac_precursor, preventivos_anio, origen
    ("Rx-L1-03", "Tanque reactor 1 100 L", "Formulación de líquidos", 1, 1, 18, 9.1, 9.1, 0.62, 0.40, 12, "Tabla 10"),
    ("Rx-L1-07", "Tanque reactor 4 000 L", "Formulación de líquidos", 1, 1, 8, 20.4, 7.9, 0.62, 0.40, 12, "Tabla 10"),
    ("Rx-L1-01", "Tanque reactor 350 L", "Formulación de líquidos", 1, 0, 5, 23.6, 14.9, 0.62, 0.40, 12, "Tabla 10"),
    ("OTR-LIQ", "Otros equipos de líquidos (agregado)", "Formulación de líquidos", 0, 0, 8, 40.15, 3.16, 0.62, 0.0, 0, "Cierre de totales"),
    ("MV-L2-02", "Mezcladora tipo V 500 kg", "Formulación de sólidos", 1, 1, 17, 19.1, 5.7, 0.62, 0.40, 12, "Tabla 10"),
    ("MH-L3-01", "Mezcladora helicoidal 250 kg", "Formulación de sólidos", 1, 0, 5, 22.4, 8.7, 0.62, 0.40, 12, "Tabla 10"),
    ("MH-L3-02", "Mezcladora helicoidal", "Formulación de sólidos", 0, 1, 8, 25.0, 5.0, 0.62, 0.40, 12, "Tabla 10 (8 fallas); MTBF y MTTR por cierre"),
    ("OTR-SOL", "Otros equipos de sólidos (agregado)", "Formulación de sólidos", 0, 0, 6, 24.28, 3.16, 0.62, 0.0, 0, "Cierre de totales"),
    ("MM-L3-01", "Molino de martillos", "Molienda de insumos", 1, 1, 22, 15.27, 5.3, 0.62, 0.40, 12, "Tabla 10"),
    ("DL-L1-01", "Dosificadora de líquidos", "Envasado de líquidos", 0, 0, 12, 16.64, 3.5, 0.30, 0.0, 24, "Sección 3.4 (12 fallas); MTBF y MTTR por cierre"),
    ("SB-L2-01", "Selladora de bolsas", "Sellado de bolsas", 0, 0, 3, 55.97, 3.2, 0.62, 0.0, 12, "Tabla 10"),
]
PREVENTIVOS_OTROS = 90      # órdenes de otros equipos: total programado = 210 (Tabla 7)
EVENTOS_NO_TECNICOS = 173   # 285 eventos (Tabla 7) − 112 fallas técnicas


def main():
    filas_eq = []
    for (cod, desc, lin, a, s, n, mtbf, mttr, fml, fpre, prev, org) in EQUIPOS:
        filas_eq.append(dict(codigo=cod, descripcion=desc, linea=lin, clase_a=a,
                             sensor_candidato=s, fallas=n, mtbf_h=mtbf, mttr_h=mttr,
                             horas_marcha=round(n * mtbf, 2),
                             frac_mec_lub=fml, frac_precursor=fpre,
                             preventivos_anio=prev, origen=org))

    filas_lin, tot_otras = [], 0.0
    for (lin, plan, disp, rend, cal, oee) in LINEAS:
        marcha = plan * disp
        tecnico = sum(e["fallas"] * e["mttr_h"] for e in filas_eq if e["linea"] == lin)
        otras = max(0.0, plan - marcha - tecnico)
        tot_otras += otras
        filas_lin.append(dict(linea=lin, tiempo_planificado_h=plan, disponibilidad=disp,
                              rendimiento=rend, calidad=cal, oee=oee,
                              horas_marcha=round(marcha, 1),
                              paradas_tecnicas_h=round(tecnico, 1),
                              otras_paradas_h=round(otras, 1)))
    dur_otras = tot_otras / EVENTOS_NO_TECNICOS
    for f in filas_lin:
        f["duracion_media_otras_h"] = round(dur_otras, 3)

    # Comprobación de cierre con los totales de planta del diagnóstico
    n_tot = sum(e["fallas"] for e in filas_eq)
    marcha_eq = sum(e["horas_marcha"] for e in filas_eq)
    marcha_lin = sum(f["horas_marcha"] for f in filas_lin)
    tec = sum(e["fallas"] * e["mttr_h"] for e in filas_eq)
    print(f"Fallas técnicas: {n_tot} (meta 112)")
    print(f"Horas de marcha por equipos: {marcha_eq:.1f} | por líneas: {marcha_lin:.1f}")
    print(f"MTBF de planta: {marcha_lin / n_tot:.2f} h (meta 20,1)")
    print(f"MTTR de planta: {tec / n_tot:.2f} h (meta 6,2)")
    print(f"Paradas totales: {tec + tot_otras:.1f} h (meta 1 032,3)")
    print(f"Duración media de paradas no técnicas: {dur_otras:.2f} h")

    with open(AQUI / "parametros_equipos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas_eq[0]))
        w.writeheader(); w.writerows(filas_eq)
    with open(AQUI / "parametros_lineas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas_lin[0]))
        w.writeheader(); w.writerows(filas_lin)


if __name__ == "__main__":
    main()
