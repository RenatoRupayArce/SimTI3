"""Ejecución de escenarios con réplicas y números aleatorios comunes."""
import pandas as pd

from .motor import simular
from .kpi import kpi_simulacion, valoracion_economica, techo_planta, brecha_cerrada
from .escenarios import Escenario, CODIGO_ASIS


def correr(parametros, escenarios, n_replicas=30, semilla_base=2026, progreso=None):
    """Devuelve (resultados de planta por réplica, resultados por línea)."""
    filas, filas_linea = [], []
    eq = parametros["equipos"]
    n_clase_a = int(eq["clase_a"].sum())
    techo = techo_planta(parametros["lineas"])
    asis = Escenario("AS-IS", niveles=escenarios[0].niveles,
                     n_tecnicos=int(parametros["generales"]["n_tecnicos"]))
    total = len(escenarios) * n_replicas
    hecho = 0
    for r in range(n_replicas):
        semilla = semilla_base + r
        sim_asis = simular(parametros, asis, semilla)
        k_asis, _ = kpi_simulacion(sim_asis)
        for esc in escenarios:
            sim = sim_asis if esc.codigo() == CODIGO_ASIS and esc.n_tecnicos == asis.n_tecnicos \
                else simular(parametros, esc, semilla)
            k, pl = kpi_simulacion(sim)
            n_sens = len(sim.sensores) if esc.iot else 0
            eco = valoracion_economica(k, k_asis, esc, parametros["economicos"], n_sens, n_clase_a)
            fila = dict(escenario=esc.nombre, codigo=esc.codigo(), A=int(esc.tpm), B=int(esc.iot),
                        replica=r, **k, **eco)
            fila["brecha_cerrada"] = brecha_cerrada(k["oee"], k_asis["oee"], techo)
            filas.append(fila)
            pl = pl.assign(escenario=esc.nombre, replica=r)
            filas_linea.append(pl)
            hecho += 1
            if progreso:
                progreso(hecho / total)
    return pd.DataFrame(filas), pd.concat(filas_linea, ignore_index=True)


def resumen(df, columnas=("oee", "disponibilidad", "mtbf_h", "mttr_h", "paradas_no_planificadas_h",
                          "brecha_cerrada", "beneficio_neto_anual", "inversion_inicial")):
    from .kpi import intervalo_confianza
    filas = []
    for esc, g in df.groupby("escenario", sort=False):
        fila = {"escenario": esc}
        for c in columnas:
            m, h = intervalo_confianza(g[c])
            fila[c] = m
            fila[c + "_ic"] = h
        filas.append(fila)
    return pd.DataFrame(filas)


def correr_sensibilidad(parametros, niveles_base, n_replicas=10, semilla_base=3030, progreso=None):
    """OEE y beneficio neto del escenario TPM + IoT al mover cada parámetro incierto."""
    from .escenarios import escenarios_sensibilidad
    integrado, lista = escenarios_sensibilidad(parametros["escenario_tabla"], niveles_base)
    base_df, _ = correr(parametros, [integrado], n_replicas, semilla_base)
    base_oee = float(base_df["oee"].mean())
    base_neto = float(base_df["beneficio_neto_anual"].mean())
    filas = []
    for i, (param, etiqueta, esc) in enumerate(lista):
        d, _ = correr(parametros, [esc], n_replicas, semilla_base)
        filas.append(dict(parametro=param, nivel=etiqueta, oee=float(d["oee"].mean()),
                          beneficio_neto=float(d["beneficio_neto_anual"].mean())))
        if progreso:
            progreso((i + 1) / len(lista))
    t = pd.DataFrame(filas)
    tabla = t.pivot(index="parametro", columns="nivel", values="oee").reset_index()
    tabla["rango_pp"] = 100 * (tabla["optimista"] - tabla["pesimista"]).abs()
    tabla = tabla.sort_values("rango_pp", ascending=False)
    return tabla, base_oee, base_neto, t
