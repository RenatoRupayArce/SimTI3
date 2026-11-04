"""K2 · Ajuste de datos de entrada y calibración del AS-IS.

- ajustar_weibull: ajusta Weibull (β, η) al tiempo entre fallas de cada equipo a
  partir de un registro de fallas y aplica la prueba de Kolmogorov–Smirnov.
- calibrar: ajusta dos factores del AS-IS (notificación y escala de fallas) para que
  el simulador reproduzca el tiempo de respuesta medio y el número de fallas de la
  línea base. Usa solo los objetivos de calibración, nunca los de prueba.
"""
import copy
import numpy as np
import pandas as pd
from scipy import stats

from .escenarios import Escenario
from .motor import simular
from .kpi import kpi_simulacion


def ajustar_weibull(registro, lotes=None, minimo_fallas=5):
    """Devuelve una tabla con β, η, MTBF y el p-valor K-S por equipo.
    El tiempo entre fallas se mide en horas de reloj de turno entre fallas sucesivas
    (aproximación cuando no se dispone de las horas de marcha por evento)."""
    fallas = registro[registro["tipo"] == "falla_tecnica"].sort_values("inicio_parada_h")
    filas = []
    for cod, g in fallas.groupby("codigo_equipo"):
        t = np.diff(g["inicio_parada_h"].to_numpy(float))
        t = t[t > 0]
        if len(t) < minimo_fallas:
            filas.append(dict(codigo_equipo=cod, n=len(t), beta=np.nan, eta=np.nan,
                              media_h=float(t.mean()) if len(t) else np.nan,
                              p_ks=np.nan, ajuste="Insuficiente (usar empírica)"))
            continue
        beta, _, eta = stats.weibull_min.fit(t, floc=0)
        p = stats.kstest(t, "weibull_min", args=(beta, 0, eta)).pvalue
        filas.append(dict(codigo_equipo=cod, n=len(t), beta=beta, eta=eta,
                          media_h=float(t.mean()), p_ks=p,
                          ajuste="Aceptado" if p > 0.05 else "Rechazado"))
    return pd.DataFrame(filas)


def calibrar(parametros, objetivo_fallas=112, objetivo_respuesta_h=None,
             n_replicas=10, iteraciones=4, semilla=7000):
    """Calibra factor_notificacion y factor_eta. Devuelve (parametros calibrados, historial)."""
    p = copy.deepcopy(parametros)
    g = p["generales"]
    objetivo_respuesta_h = objetivo_respuesta_h or g["respuesta_media_h"]
    g.setdefault("factor_notificacion", 1.0)
    g.setdefault("factor_eta", 1.0)
    historial = []
    for it in range(iteraciones):
        ks = [kpi_simulacion(simular(p, Escenario("AS-IS", niveles={}), semilla + r))[0]
              for r in range(n_replicas)]
        resp = float(np.mean([k["mttr_respuesta_h"] for k in ks]))
        nf = float(np.mean([k["fallas"] for k in ks]))
        historial.append(dict(iteracion=it + 1, factor_notificacion=g["factor_notificacion"],
                              factor_eta=g["factor_eta"], respuesta_media_h=resp, fallas=nf))
        g["factor_notificacion"] *= objetivo_respuesta_h / resp
        g["factor_eta"] *= nf / objetivo_fallas
    return p, pd.DataFrame(historial)
