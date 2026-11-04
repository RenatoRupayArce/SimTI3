"""Pruebas de verificación del modelo computarizado (Tabla de pruebas V01–V08).

Ejecutar desde la carpeta del proyecto:  python pruebas/verificacion.py
"""
import copy
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from simti.datos import cargar_parametros, niveles_escenario
from simti.escenarios import Escenario
from simti.motor import simular
from simti.kpi import kpi_simulacion

TOL = 1e-6


def _asis(p, semilla=11, **kw):
    return simular(p, Escenario("AS-IS", niveles=niveles_escenario(p), **kw), semilla)


def v01_ejecucion(p):
    sim = _asis(p)
    k, _ = kpi_simulacion(sim)
    ok = k["lotes_terminados"] == len(sim.lotes) and len(sim.lotes) > 0
    return ok, f"{len(sim.lotes)} lotes terminados en {p['generales']['horizonte_h']:.0f} h de turno"


def v02_conservacion(p):
    sim = _asis(p)
    ev = pd.DataFrame(sim.eventos)
    ev = ev[ev["tipo"].isin(["falla_tecnica", "no_tecnica"])]
    par = ev.assign(d=ev.fin_parada_h - ev.inicio_parada_h).groupby("id_lote")["d"].sum()
    malos = 0
    for l in sim.lotes:
        duracion = l["fin_h"] - l["inicio_h"]
        if abs(duracion - (l["marcha_h"] + l["paradas_h"])) > 1e-6:
            malos += 1
        if abs(l["paradas_h"] - par.get(l["id_lote"], 0.0)) > 1e-6:
            malos += 1
    return malos == 0, f"Lotes que incumplen (duración = marcha + paradas): {malos} de {len(sim.lotes)}"


def v03_capacidad(p):
    sim = _asis(p)
    lt = pd.DataFrame(sim.lotes)
    marcha_eq = p["equipos"].set_index("codigo")["horas_marcha"]
    real = lt.groupby("codigo_equipo")["marcha_h"].sum()
    desvio = ((real - marcha_eq) / marcha_eq).abs().max()
    solapes = 0
    for _, g in lt.sort_values("inicio_h").groupby("codigo_equipo"):
        solapes += int((g["inicio_h"].to_numpy()[1:] < g["fin_h"].to_numpy()[:-1] - TOL).sum())
    ok = solapes == 0 and desvio < 0.25
    return ok, (f"Lotes simultáneos en un mismo equipo: {solapes}; desviación máxima de horas de "
                f"marcha frente a la línea base: {desvio:.1%}")


def v04_descomposicion(p):
    sim = _asis(p)
    ev = pd.DataFrame(sim.eventos)
    f = ev[ev.tipo == "falla_tecnica"]
    rep = f.fin_parada_h - f.inicio_atencion_h - f.espera_repuesto_h
    ok = bool((rep >= -TOL).all() and (f.inicio_atencion_h >= f.inicio_parada_h - TOL).all())
    return ok, f"{len(f)} fallas: respuesta + espera + reparación = duración, sin componentes negativos"


def v05_sin_fallas(p):
    q = copy.deepcopy(p)
    q["equipos"]["fallas"] = 0
    q["lineas"]["otras_paradas_h"] = 0.0
    k, _ = kpi_simulacion(_asis(q))
    ok = abs(k["disponibilidad"] - 1.0) < TOL and k["fallas"] == 0
    return ok, f"Con MTBF infinito y sin paradas no técnicas: disponibilidad = {k['disponibilidad']:.4f}"


def v06_iot_ideal(p):
    """Caso extremo IoT ideal: toda falla da señal previa, se detecta y se anticipa.
    En los equipos con sensor no debe quedar ninguna falla con parada, y cada OT
    programada debe enlazar con una alerta anticipada."""
    q = copy.deepcopy(p)
    eq = q["equipos"]
    con_sensor = eq["sensor_candidato"] == 1
    eq.loc[con_sensor, "frac_precursor"] = 1.0
    niv = niveles_escenario(q)
    niv.update(p_deteccion=1.0, frac_anticipada=1.0)
    sim = simular(q, Escenario("IoT ideal", iot=True, niveles=niv), 11)
    ev = pd.DataFrame(sim.eventos)
    al = pd.DataFrame(sim.alertas)
    sens = set(eq.loc[con_sensor, "codigo"])
    fallas_sens = int(((ev.tipo == "falla_tecnica") & ev.codigo_equipo.isin(sens)).sum())
    ots = ev[ev.tipo == "ot_programada"]
    anticipadas = set(al.loc[al.tipo == "anticipada", "id_alerta"])
    enlazadas = bool(ots["id_alerta"].isin(anticipadas).all()) and len(ots) > 0
    ok = fallas_sens == 0 and enlazadas
    return ok, (f"Con detección y anticipación al 100 %: fallas con parada en equipos con sensor = "
                f"{fallas_sens}; {len(ots)} OT programadas, todas enlazadas a una alerta anticipada")


def v07_traza(p):
    sim = _asis(p)
    ev = pd.DataFrame(sim.eventos)
    f = ev[(ev.tipo == "falla_tecnica") & (ev.espera_repuesto_h > 0)].head(1)
    if f.empty:
        return False, "No se encontró un lote interrumpido con espera de repuesto"
    r = f.iloc[0]
    lote = next(l for l in sim.lotes if l["id_lote"] == r.id_lote)
    orden = lote["inicio_h"] <= r.inicio_parada_h <= r.inicio_atencion_h <= r.fin_parada_h <= lote["fin_h"]
    traza = (f"Lote {r.id_lote}: inicio {lote['inicio_h']:.2f} h → falla {r.inicio_parada_h:.2f} h → "
             f"atención {r.inicio_atencion_h:.2f} h → espera de repuesto {r.espera_repuesto_h:.2f} h → "
             f"fin de reparación {r.fin_parada_h:.2f} h → fin del lote {lote['fin_h']:.2f} h")
    return bool(orden), traza


def v08_reproducibilidad(p):
    k1, _ = kpi_simulacion(_asis(p, 5))
    k2, _ = kpi_simulacion(_asis(p, 5))
    return math.isclose(k1["oee"], k2["oee"]), f"Misma semilla, mismo OEE: {k1['oee']:.6f} = {k2['oee']:.6f}"


PRUEBAS = [("V01", "Ejecución completa", v01_ejecucion),
           ("V02", "Conservación del tiempo", v02_conservacion),
           ("V03", "Capacidad y secuencia de lotes", v03_capacidad),
           ("V04", "Descomposición del MTTR", v04_descomposicion),
           ("V05", "Caso extremo sin fallas", v05_sin_fallas),
           ("V06", "Caso extremo con IoT ideal", v06_iot_ideal),
           ("V07", "Traza de un lote interrumpido", v07_traza),
           ("V08", "Reproducibilidad (números aleatorios comunes)", v08_reproducibilidad)]


def ejecutar_todas(p=None):
    p = p or cargar_parametros()
    filas = []
    for cod, nombre, f in PRUEBAS:
        ok, detalle = f(p)
        filas.append(dict(ID=cod, Prueba=nombre, Resultado="Aprobada" if ok else "Fallida",
                          Detalle=detalle))
    return pd.DataFrame(filas)


if __name__ == "__main__":
    pd.set_option("display.max_colwidth", 200)
    pd.set_option("display.width", 250)
    print(ejecutar_todas().to_string(index=False))
