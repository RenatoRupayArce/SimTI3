"""K1 · Repositorio de datos: carga y valida los parámetros y los registros."""
from pathlib import Path
import pandas as pd

CARPETA_DATOS = Path(__file__).resolve().parent.parent / "datos"

COLUMNAS_REGISTRO = ["id_evento", "codigo_equipo", "linea", "tipo", "categoria",
                     "inicio_parada_h", "inicio_atencion_h", "espera_repuesto_h",
                     "fin_parada_h", "id_lote"]


def _tabla_a_dict(df, col_valor="valor"):
    return {r.parametro: float(getattr(r, col_valor)) for r in df.itertuples()}


def cargar_parametros(carpeta=CARPETA_DATOS):
    """Devuelve un diccionario con todas las tablas de entrada del simulador."""
    carpeta = Path(carpeta)
    equipos = pd.read_csv(carpeta / "parametros_equipos.csv")
    lineas = pd.read_csv(carpeta / "parametros_lineas.csv")
    generales = pd.read_csv(carpeta / "parametros_generales.csv")
    escenario = pd.read_csv(carpeta / "parametros_escenario.csv")
    economicos = pd.read_csv(carpeta / "parametros_economicos.csv")
    p = {
        "equipos": equipos,
        "lineas": lineas,
        "generales": _tabla_a_dict(generales),
        "escenario_tabla": escenario,
        "economicos": _tabla_a_dict(economicos),
        "tablas_fuente": {"generales": generales, "economicos": economicos},
    }
    validar_parametros(p)
    return p


def validar_parametros(p):
    """Reglas de calidad de datos (actividad A1.2). Lanza ValueError si falla una."""
    eq, ln = p["equipos"], p["lineas"]
    errores = []
    if eq["codigo"].duplicated().any():
        errores.append("Hay códigos de equipo duplicados.")
    huerfanos = set(eq["linea"]) - set(ln["linea"])
    if huerfanos:
        errores.append(f"Equipos con línea inexistente: {huerfanos}")
    for col in ["fallas", "mtbf_h", "mttr_h", "horas_marcha"]:
        if (eq[col] < 0).any():
            errores.append(f"Valores negativos en {col}.")
    for col in ["disponibilidad", "rendimiento", "calidad"]:
        if ((ln[col] <= 0) | (ln[col] > 1)).any():
            errores.append(f"{col} fuera de (0, 1].")
    if ((eq["frac_mec_lub"] < 0) | (eq["frac_mec_lub"] > 1)).any():
        errores.append("frac_mec_lub fuera de [0, 1].")
    if errores:
        raise ValueError(" | ".join(errores))
    return True


def niveles_escenario(p, nivel="base"):
    """Parámetros del escenario TO-BE en el nivel pedido (pesimista, base, optimista)."""
    t = p["escenario_tabla"]
    return {r.parametro: float(getattr(r, nivel)) for r in t.itertuples()}


def leer_registro_fallas(archivo):
    """Lee un registro de fallas con la estructura de la plantilla (taxonomía ISO 14224)."""
    df = pd.read_csv(archivo)
    faltan = [c for c in COLUMNAS_REGISTRO if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas en el registro: {faltan}")
    return df
