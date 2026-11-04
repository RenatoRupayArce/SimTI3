"""K1b · Registros de planta en Excel: lectura, validación y resúmenes TPM e IoT.

El libro Excel (plantilla en datos/plantilla_registros_CBI.xlsx) tiene estas hojas:

    Configuracion  parámetros del calendario de turnos y naturaleza de los datos
    Equipos        equipos de la planta (clase A, sensor IoT)
    Paradas        registro de paradas: fallas técnicas, paradas no técnicas y OT programadas
    Lotes          registro de lotes por equipo
    Preventivos    plan de mantenimiento TPM y su ejecución            (opcional)
    Sensores       sensores IoT instalados por equipo                   (opcional)
    Lecturas_IoT   lecturas de los sensores                             (opcional)
    Alertas_IoT    alertas generadas por la plataforma IoT              (opcional)

Las fechas se convierten a «horas de turno» con el calendario de la hoja Configuracion,
la misma unidad de tiempo del simulador. También se aceptan columnas ya expresadas en horas.
Este módulo no se conecta a sensores: solo lee lo que la empresa registra en el Excel.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

DIAS = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5, "dom": 6}

COLUMNAS = {
    "Equipos": ["codigo", "descripcion", "linea", "clase_a", "sensor_iot"],
    "Paradas": ["id_evento", "codigo_equipo", "linea", "tipo", "categoria", "inicio_parada",
                "inicio_atencion", "espera_repuesto_h", "fin_parada", "id_lote", "id_alerta"],
    "Lotes": ["id_lote", "codigo_equipo", "linea", "llegada", "inicio", "fin", "marcha_std_h",
              "marcha_h", "paradas_h"],
    "Preventivos": ["id_orden", "codigo_equipo", "actividad", "origen", "id_alerta",
                    "fecha_programada", "inicio_ejecucion", "fin_ejecucion", "responsable",
                    "ejecutado_por", "observacion"],
    "Sensores": ["sensor_id", "codigo_equipo", "variable", "unidad", "limite_alerta"],
    "Lecturas_IoT": ["fecha_hora", "sensor_id", "valor"],
    "Alertas_IoT": ["id_alerta", "fecha_hora", "codigo_equipo", "sensor_id", "tipo", "resultado"],
}
OBLIGATORIAS = ("Paradas", "Lotes")
OPCIONALES_VACIAS = ("id_alerta", "id_lote", "categoria", "responsable", "actividad", "origen",
                     "resultado", "sensor_id", "descripcion", "ejecutado_por", "observacion",
                     "fin_ejecucion")
TIPOS_PARADA = ("falla_tecnica", "no_tecnica", "ot_programada")
TIPOS_ALERTA = ("anticipada", "tardía", "falsa")

CONFIG_DEFECTO = {
    "inicio_periodo": None,          # vacío = la fecha más antigua de Paradas y Lotes
    "hora_inicio_turno": 7.0,
    "horas_por_turno": 8.0,
    "dias_laborables": "lun-sab",
    "fecha_corte": None,
    "naturaleza_datos": "Sin especificar",
}


# ------------------------------------------------------------------ calendario de turnos
class Calendario:
    """Convierte fecha y hora ↔ horas de turno (el reloj solo corre dentro del turno)."""

    def __init__(self, inicio, hora_inicio=7.0, horas_turno=8.0, dias="lun-sab"):
        self.inicio = np.datetime64(pd.Timestamp(inicio).date(), "D")
        self.hora_inicio = float(hora_inicio)
        self.horas = float(horas_turno)
        self.mascara = _mascara(dias)

    def a_horas(self, valores):
        ts = pd.to_datetime(pd.Series(valores), errors="coerce", dayfirst=True)
        salida = np.full(len(ts), np.nan)
        ok = ts.notna().to_numpy()
        if ok.any():
            t = ts[ok]
            dias = t.dt.normalize().to_numpy().astype("datetime64[D]")
            idx = np.busday_count(self.inicio, dias, weekmask=self.mascara)
            habil = np.is_busday(dias, weekmask=self.mascara)
            hora = (t.dt.hour + t.dt.minute / 60 + t.dt.second / 3600).to_numpy()
            dentro = np.clip(hora - self.hora_inicio, 0.0, self.horas)
            dentro = np.where(habil, dentro, 0.0)
            salida[ok] = idx * self.horas + dentro
        return salida

    def a_fecha(self, horas, es_fin=False):
        h = float(horas)
        idx = int(h // self.horas)
        dentro = h - idx * self.horas
        if es_fin and dentro < 1e-9 and h > 0:
            idx, dentro = idx - 1, self.horas
        dia = np.busday_offset(self.inicio, idx, roll="forward", weekmask=self.mascara)
        base = datetime.combine(pd.Timestamp(dia).date(), datetime.min.time())
        return base + timedelta(hours=self.hora_inicio + dentro)


def _mascara(texto):
    texto = str(texto).lower().replace(" ", "")
    if "-" in texto and "," not in texto:
        a, b = texto.split("-")
        dias = range(DIAS.get(a[:3], 0), DIAS.get(b[:3], 5) + 1)
    else:
        dias = [DIAS[d[:3]] for d in texto.split(",") if d[:3] in DIAS]
    return "".join("1" if i in dias else "0" for i in range(7))


# ------------------------------------------------------------------ lectura del libro
@dataclass
class Registros:
    eventos: pd.DataFrame
    lotes: pd.DataFrame
    equipos: pd.DataFrame
    preventivos: pd.DataFrame
    sensores: pd.DataFrame
    lecturas: pd.DataFrame
    alertas: pd.DataFrame
    config: dict
    calendario: Calendario
    fecha_corte: datetime
    avisos: list = field(default_factory=list)
    errores: list = field(default_factory=list)

    @property
    def sintetico(self):
        return "sint" in str(self.config.get("naturaleza_datos", "")).lower()

    @property
    def tiene_iot(self):
        return not self.sensores.empty

    @property
    def tiene_tpm(self):
        return not self.preventivos.empty


def _limpiar(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.dropna(how="all")
    return df


def _leer_config(hojas):
    cfg = dict(CONFIG_DEFECTO)
    if "Configuracion" in hojas:
        c = _limpiar(hojas["Configuracion"])
        if {"parametro", "valor"} <= set(c.columns):
            for r in c.itertuples():
                clave = str(r.parametro).strip().lower()
                if clave in cfg and pd.notna(r.valor) and str(r.valor).strip() != "":
                    cfg[clave] = r.valor
    for clave in ("hora_inicio_turno", "horas_por_turno"):
        v = cfg[clave]
        if isinstance(v, (datetime, pd.Timestamp)):
            v = v.hour + v.minute / 60
        elif hasattr(v, "hour"):
            v = v.hour + v.minute / 60
        elif isinstance(v, str) and ":" in v:
            hh, mm = v.split(":")[:2]
            v = int(hh) + int(mm) / 60
        cfg[clave] = float(v)
    return cfg


def _a_horas(df, columnas, cal, es_fin=()):
    for c in columnas:
        if c not in df:
            continue
        col = df[c]
        if pd.api.types.is_numeric_dtype(col):
            df[c + "_h"] = col.astype(float)
        else:
            df[c + "_h"] = cal.a_horas(col)
    return df


def leer_excel(archivo, equipos_modelo=None):
    """Lee el libro de registros. Nunca lanza excepción por datos: devuelve errores y avisos."""
    errores, avisos = [], []
    try:
        hojas = pd.read_excel(archivo, sheet_name=None)
    except Exception as exc:  # archivo dañado o no es Excel
        return None, [f"No se pudo leer el archivo Excel: {exc}"]
    cfg = _leer_config(hojas)
    if cfg["inicio_periodo"] is None or str(cfg["inicio_periodo"]).strip() in ("", "nan", "NaT"):
        fechas = []
        for hoja, cols in (("Paradas", ("inicio_parada",)), ("Lotes", ("llegada", "inicio"))):
            if hoja in hojas:
                d = _limpiar(hojas[hoja])
                for c in cols:
                    if c in d and not pd.api.types.is_numeric_dtype(d[c]):
                        fechas.append(pd.to_datetime(d[c], errors="coerce", dayfirst=True).min())
        fechas = [f for f in fechas if pd.notna(f)]
        cfg["inicio_periodo"] = min(fechas).date() if fechas else date(2024, 1, 2)
    cal = Calendario(cfg["inicio_periodo"], cfg["hora_inicio_turno"], cfg["horas_por_turno"],
                     cfg["dias_laborables"])

    tablas = {}
    for hoja, cols in COLUMNAS.items():
        if hoja not in hojas:
            if hoja in OBLIGATORIAS:
                errores.append(f"Falta la hoja obligatoria «{hoja}».")
            tablas[hoja] = pd.DataFrame(columns=cols)
            continue
        df = _limpiar(hojas[hoja])
        faltan = [c for c in cols if c not in df.columns and c not in OPCIONALES_VACIAS]
        if faltan:
            (errores if hoja in OBLIGATORIAS else avisos).append(
                f"Hoja «{hoja}»: faltan las columnas {', '.join(faltan)}.")
            if hoja not in OBLIGATORIAS:
                df = pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df.columns:
                df[c] = np.nan if c not in OPCIONALES_VACIAS else ""
        tablas[hoja] = df
    if errores:
        return None, errores

    # ---- equipos
    eq = tablas["Equipos"]
    if eq.empty and equipos_modelo is not None:
        eq = equipos_modelo.rename(columns={"sensor_candidato": "sensor_iot"})[
            ["codigo", "descripcion", "linea", "clase_a", "sensor_iot"]].copy()
        avisos.append("La hoja «Equipos» está vacía: se usan los equipos del modelo.")
    for c in ("clase_a", "sensor_iot"):
        eq[c] = eq[c].map(_si_no).fillna(0).astype(int)

    # ---- paradas
    ev = tablas["Paradas"].copy()
    ev["tipo"] = ev["tipo"].astype(str).str.strip().str.lower()
    malos = ~ev["tipo"].isin(TIPOS_PARADA)
    if malos.any():
        avisos.append(f"Paradas: {int(malos.sum())} filas con un tipo no reconocido se ignoraron "
                      f"(válidos: {', '.join(TIPOS_PARADA)}).")
        ev = ev[~malos]
    ev = _a_horas(ev, ["inicio_parada", "inicio_atencion", "fin_parada"], cal)
    ev["inicio_atencion_h"] = ev["inicio_atencion_h"].fillna(ev["inicio_parada_h"])
    ev["espera_repuesto_h"] = pd.to_numeric(ev["espera_repuesto_h"], errors="coerce").fillna(0.0)
    sin_t = ev["inicio_parada_h"].isna() | ev["fin_parada_h"].isna()
    if sin_t.any():
        avisos.append(f"Paradas: {int(sin_t.sum())} filas sin fecha de inicio o fin se ignoraron.")
        ev = ev[~sin_t]
    neg = ev["fin_parada_h"] < ev["inicio_parada_h"]
    if neg.any():
        avisos.append(f"Paradas: {int(neg.sum())} filas con fin anterior al inicio se ignoraron.")
        ev = ev[~neg]
    eventos = pd.DataFrame({
        "id_evento": ev["id_evento"], "codigo_equipo": ev["codigo_equipo"].astype(str),
        "linea": ev["linea"], "tipo": ev["tipo"], "categoria": ev["categoria"].fillna(""),
        "inicio_parada_h": ev["inicio_parada_h"], "inicio_atencion_h": ev["inicio_atencion_h"],
        "espera_repuesto_h": ev["espera_repuesto_h"], "fin_parada_h": ev["fin_parada_h"],
        "id_lote": ev["id_lote"].fillna(""), "id_alerta": ev["id_alerta"].fillna("").astype(str),
    }).reset_index(drop=True)

    # ---- lotes
    lt = tablas["Lotes"].copy()
    lt = _a_horas(lt, ["llegada", "inicio", "fin"], cal)
    for c in ("marcha_std_h", "marcha_h", "paradas_h"):
        lt[c] = pd.to_numeric(lt[c], errors="coerce")
    lotes = pd.DataFrame({
        "id_lote": lt["id_lote"], "codigo_equipo": lt["codigo_equipo"].astype(str), "linea": lt["linea"],
        "llegada_h": lt["llegada_h"].fillna(lt["inicio_h"]), "inicio_h": lt["inicio_h"],
        "fin_h": lt["fin_h"], "marcha_std_h": lt["marcha_std_h"].fillna(lt["marcha_h"]),
        "marcha_h": lt["marcha_h"].fillna(0.0), "paradas_h": lt["paradas_h"].fillna(0.0),
    }).reset_index(drop=True)
    if lotes.empty or lotes["inicio_h"].isna().all():
        return None, ["La hoja «Lotes» no tiene registros válidos: es obligatoria para calcular "
                      "la disponibilidad y el OEE. Complete Paradas y Lotes y vuelva a subir el archivo."]
    lineas_desconocidas = set(eventos["linea"].dropna()) | set(lotes["linea"].dropna())
    if equipos_modelo is not None:
        lineas_desconocidas -= set(equipos_modelo["linea"])
        if lineas_desconocidas:
            avisos.append("Líneas que no existen en el modelo (no entran al OEE por línea): "
                          + ", ".join(sorted(map(str, lineas_desconocidas))))

    # ---- fecha de corte
    candidatos = []
    for serie in (ev.get("fin_parada"), lt.get("fin")):
        if serie is not None and not pd.api.types.is_numeric_dtype(serie):
            candidatos.append(pd.to_datetime(serie, errors="coerce", dayfirst=True).max())
    corte = cfg.get("fecha_corte")
    if corte is None or (isinstance(corte, float) and np.isnan(corte)) or str(corte).strip() == "":
        corte = max([c for c in candidatos if pd.notna(c)], default=None)
        if corte is None:
            corte = cal.a_fecha(max(lotes["fin_h"].max(), eventos["fin_parada_h"].max()), es_fin=True)
    corte = pd.Timestamp(corte).to_pydatetime()
    if corte.hour == 0 and corte.minute == 0:
        corte = corte + timedelta(hours=cfg["hora_inicio_turno"] + cfg["horas_por_turno"])

    # ---- TPM
    pv = tablas["Preventivos"].copy()
    if not pv.empty:
        for c in ("fecha_programada", "inicio_ejecucion", "fin_ejecucion"):
            pv[c] = pd.to_datetime(pv[c], errors="coerce", dayfirst=True)
        pv["origen"] = pv["origen"].replace("", np.nan).fillna("Plan preventivo")
        pv["estado"] = np.where(pv["inicio_ejecucion"].notna() & (pv["inicio_ejecucion"] <= corte),
                                "Realizada",
                                np.where(pv["fecha_programada"] > corte, "Pendiente", "Vencida"))
        for c in ("id_alerta", "ejecutado_por", "observacion", "responsable", "actividad"):
            pv[c] = pv[c].fillna("").astype(str).replace("nan", "")
        pv["codigo_equipo"] = pv["codigo_equipo"].astype(str)

    # ---- IoT
    se = tablas["Sensores"].copy()
    if not se.empty:
        se["limite_alerta"] = pd.to_numeric(se["limite_alerta"], errors="coerce")
        se["sensor_id"] = se["sensor_id"].astype(str)
        se["codigo_equipo"] = se["codigo_equipo"].astype(str)
    lec = tablas["Lecturas_IoT"].copy()
    if not lec.empty:
        lec["fecha_hora"] = pd.to_datetime(lec["fecha_hora"], errors="coerce", dayfirst=True)
        lec["valor"] = pd.to_numeric(lec["valor"], errors="coerce")
        lec["sensor_id"] = lec["sensor_id"].astype(str)
        lec = lec.dropna(subset=["fecha_hora", "valor"])
        lec = lec[lec["fecha_hora"] <= corte]
        desconocidos = set(lec["sensor_id"]) - set(se["sensor_id"])
        if desconocidos:
            avisos.append(f"Lecturas de {len(desconocidos)} sensores que no están en la hoja «Sensores».")
    al = tablas["Alertas_IoT"].copy()
    if not al.empty:
        al["fecha_hora"] = pd.to_datetime(al["fecha_hora"], errors="coerce", dayfirst=True)
        al["tipo"] = al["tipo"].astype(str).str.strip().str.lower()
        al["id_alerta"] = al["id_alerta"].astype(str)
        al["codigo_equipo"] = al["codigo_equipo"].astype(str)
        al = al[al["fecha_hora"] <= corte]

    reg = Registros(eventos=eventos, lotes=lotes, equipos=eq.reset_index(drop=True),
                    preventivos=pv.reset_index(drop=True), sensores=se.reset_index(drop=True),
                    lecturas=lec.reset_index(drop=True), alertas=al.reset_index(drop=True),
                    config=cfg, calendario=cal, fecha_corte=corte, avisos=avisos)
    return reg, []


def _si_no(v):
    if isinstance(v, str):
        return 1 if v.strip().lower() in ("sí", "si", "s", "yes", "1", "x") else 0
    try:
        return int(bool(int(v)))
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ resúmenes
def kpi_por_equipo(eventos, lotes):
    """Disponibilidad, fallas, MTBF y MTTR por equipo (misma definición que la de planta)."""
    ev = eventos.assign(d=eventos["fin_parada_h"] - eventos["inicio_parada_h"])
    no_planif = ev[ev["tipo"].isin(["falla_tecnica", "no_tecnica"])]
    fallas = ev[ev["tipo"] == "falla_tecnica"]
    marcha = lotes.groupby("codigo_equipo")["marcha_h"].sum()
    paradas = no_planif.groupby("codigo_equipo")["d"].sum()
    n = fallas.groupby("codigo_equipo").size()
    mttr = fallas.groupby("codigo_equipo")["d"].mean()
    t = pd.DataFrame({"horas_marcha": marcha, "horas_parada": paradas, "fallas": n, "mttr_h": mttr})
    t = t.fillna({"horas_marcha": 0.0, "horas_parada": 0.0, "fallas": 0})
    plan = t["horas_marcha"] + t["horas_parada"]
    t["disponibilidad"] = np.where(plan > 0, t["horas_marcha"] / plan.where(plan > 0, 1), np.nan)
    t["mtbf_h"] = np.where(t["fallas"] > 0, t["horas_marcha"] / t["fallas"].where(t["fallas"] > 0, 1), np.nan)
    t["fallas"] = t["fallas"].astype(int)
    t.index.name = "codigo_equipo"
    return t.reset_index()


def resumen_tpm(preventivos):
    """Programadas, realizadas, vencidas, pendientes y cumplimiento por equipo."""
    if preventivos.empty:
        return pd.DataFrame(columns=["codigo_equipo", "Realizada", "Vencida", "Pendiente", "cumplimiento"])
    t = preventivos.pivot_table(index="codigo_equipo", columns="estado", values="id_orden",
                                aggfunc="count", fill_value=0)
    for c in ("Realizada", "Vencida", "Pendiente"):
        if c not in t:
            t[c] = 0
    vencidas_o_hechas = t["Realizada"] + t["Vencida"]
    t["cumplimiento"] = np.where(vencidas_o_hechas > 0, t["Realizada"] / vencidas_o_hechas.where(vencidas_o_hechas > 0, 1), np.nan)
    t["por_alerta"] = preventivos[preventivos["origen"].str.contains("IoT", case=False, na=False)] \
        .groupby("codigo_equipo").size().reindex(t.index).fillna(0).astype(int)
    return t.reset_index()[["codigo_equipo", "Realizada", "Vencida", "Pendiente", "cumplimiento", "por_alerta"]]


def estado_sensores(sensores, lecturas, referencia):
    """Última lectura, estado frente al límite y estado de transmisión inferido por sensor.

    La «conexión» se infiere de la antigüedad de la última lectura registrada: el sistema
    no tiene un enlace en tiempo real con los sensores."""
    if sensores.empty:
        return pd.DataFrame()
    filas = []
    for s in sensores.itertuples():
        l = lecturas[lecturas["sensor_id"] == s.sensor_id].sort_values("fecha_hora") if not lecturas.empty \
            else pd.DataFrame()
        if l.empty:
            filas.append(dict(sensor_id=s.sensor_id, codigo_equipo=s.codigo_equipo, variable=s.variable,
                              unidad=s.unidad, limite_alerta=s.limite_alerta, ultima_lectura=pd.NaT,
                              ultimo_valor=np.nan, n_lecturas=0, fuera_limite=0,
                              transmision="Sin lecturas", condicion="Sin datos"))
            continue
        ultima = l.iloc[-1]
        paso = l["fecha_hora"].diff().median()
        tolerancia = max(pd.Timedelta(hours=24), 3 * paso) if pd.notna(paso) else pd.Timedelta(hours=24)
        transmite = (pd.Timestamp(referencia) - ultima["fecha_hora"]) <= tolerancia
        lim = s.limite_alerta
        fuera = int((l["valor"] > lim).sum()) if pd.notna(lim) else 0
        cond = "Sin límite" if pd.isna(lim) else ("Fuera de límite" if ultima["valor"] > lim else "Normal")
        filas.append(dict(sensor_id=s.sensor_id, codigo_equipo=s.codigo_equipo, variable=s.variable,
                          unidad=s.unidad, limite_alerta=lim, ultima_lectura=ultima["fecha_hora"],
                          ultimo_valor=float(ultima["valor"]), n_lecturas=len(l), fuera_limite=fuera,
                          transmision="Transmitiendo" if transmite else "Sin datos recientes",
                          condicion=cond))
    return pd.DataFrame(filas)


def libro_actualizado(contenido, preventivos):
    """Devuelve el libro Excel original con la hoja «Preventivos» actualizada (órdenes
    registradas desde la aplicación por el técnico)."""
    import io
    hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None)
    leeme = pd.read_excel(io.BytesIO(contenido), sheet_name="LEEME", header=None) if "LEEME" in hojas else None
    pv = preventivos.copy()
    for c in COLUMNAS["Preventivos"]:
        if c not in pv:
            pv[c] = ""
    hojas["Preventivos"] = pv[COLUMNAS["Preventivos"]]
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as w:
        for nombre, df in hojas.items():
            if nombre == "LEEME" and leeme is not None:
                leeme.to_excel(w, sheet_name=nombre, index=False, header=False)
            else:
                df.to_excel(w, sheet_name=nombre, index=False)
    return salida.getvalue()
