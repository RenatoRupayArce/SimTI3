"""K4 · Motor DES producción–mantenimiento, con los submodelos K5 (TPM y repuestos)
y K6 (IoT y alertas). R2 v2: sin el factor stock de repuestos.

Unidad de tiempo: hora de turno (un solo turno; el reloj no corre fuera de turno).
Lógica por equipo (Figura 4): lote → marcha → [falla | parada no técnica | alerta]
→ notificación → espera de técnico → espera de repuesto → reparación → reanuda.
"""
import math
import zlib
import numpy as np

from .nucleo import Entorno, Recurso

HORAS_MES = 208.0  # 26 días × 8 h


def _rng(semilla, *claves):
    """Flujo aleatorio independiente por réplica, equipo y proceso
    (números aleatorios comunes entre escenarios)."""
    h = zlib.crc32("|".join(map(str, claves)).encode())
    return np.random.default_rng([int(semilla), h])


def _lognormal(rng, media, cv):
    if media <= 0:
        return 0.0
    s2 = math.log(1 + cv ** 2)
    mu = math.log(media) - s2 / 2
    return float(rng.lognormal(mu, math.sqrt(s2)))


def _weibull(rng, eta, beta):
    return float(eta * rng.weibull(beta))


class Simulacion:
    def __init__(self, parametros, escenario, semilla=1):
        self.p = parametros
        self.g = parametros["generales"]
        self.esc = escenario
        self.niv = escenario.niveles
        self.semilla = semilla
        self.env = Entorno()
        self.tecnicos = Recurso(self.env, escenario.n_tecnicos)
        self.T = self.g["horizonte_h"]
        self.eventos, self.lotes, self.preventivos, self.alertas = [], [], [], []
        self.horas_tecnico = 0.0
        self._id = 0
        eq = parametros["equipos"]
        self.sensores = set(escenario.equipos_sensor) if escenario.equipos_sensor else \
            set(eq.loc[eq["sensor_candidato"] == 1, "codigo"])
        lin = parametros["lineas"].set_index("linea")
        self.marcha_linea = eq.groupby("linea")["horas_marcha"].sum()
        self.otras_linea = lin["otras_paradas_h"]
        self.dur_otras = float(lin["duracion_media_otras_h"].iloc[0])
        self.marcha_total = float(eq["horas_marcha"].sum())

    # ------------------------------------------------------------------ utilidades
    def _nuevo_id(self):
        self._id += 1
        return self._id

    def _tpm_activo(self, e):
        return self.esc.tpm and int(e["clase_a"]) == 1

    def _iot_activo(self, e):
        return self.esc.iot and e["codigo"] in self.sensores

    # ------------------------------------------------------------------ construcción
    def ejecutar(self):
        for _, e in self.p["equipos"].iterrows():
            self.env.proceso(self._equipo(e))
            if int(e["preventivos_anio"]) > 0:
                self.env.proceso(self._preventivo(e["codigo"], int(e["preventivos_anio"]),
                                                  self._tpm_activo(e)))
            if self._iot_activo(e):
                self.env.proceso(self._falsas_alarmas(e))
        self.env.proceso(self._preventivo("OTROS", 90, False))
        self.env.ejecutar(self.T)
        return self

    # ------------------------------------------------------------------ K4: equipo
    def _equipo(self, e):
        cod, g, niv = e["codigo"], self.g, self.niv
        r_lote = _rng(self.semilla, cod, "lotes")
        r_fal = _rng(self.semilla, cod, "fallas")
        r_rep = _rng(self.semilla, cod, "reparacion")
        r_otr = _rng(self.semilla, cod, "otras")
        r_iot = _rng(self.semilla, cod, "iot")

        marcha = float(e["horas_marcha"])
        n_lotes = max(1, round(g["n_lotes"] * marcha / self.marcha_total))
        llegadas = np.sort(r_lote.uniform(0, 0.92 * self.T, n_lotes))
        marchas = [_lognormal(r_lote, marcha / n_lotes, g["cv_lote"]) for _ in range(n_lotes)]

        # Relojes de falla en horas de marcha: modo A (mecánico/lubricación) y modo B (otros)
        beta = g["beta_weibull"]
        n = float(e["fallas"])
        gam = math.gamma(1 + 1 / beta)
        fml = float(e["frac_mec_lub"])
        f_eta = g.get("factor_eta", 1.0)   # calibración K2 del número de fallas
        eta_a = f_eta * (marcha / (n * fml)) / gam if n * fml > 0 else math.inf
        eta_b = f_eta * (marcha / (n * (1 - fml))) / gam if n * (1 - fml) > 0 else math.inf
        if self._tpm_activo(e):  # K5: el preventivo eleva la escala η del modo A
            c_asis = g["cumplimiento_preventivo_asis"]
            mejora = (niv["cumplimiento_preventivo_tobe"] - c_asis) / (1 - c_asis)
            eta_a *= 1 + niv["delta_tpm_mtbf"] * mejora
        nuevo = lambda eta: _weibull(r_fal, eta, beta) if math.isfinite(eta) else math.inf

        # Paradas no técnicas (insumos, auxiliares): exógenas, iguales en todos los escenarios
        otras_h = float(self.otras_linea[e["linea"]]) * marcha / float(self.marcha_linea[e["linea"]])
        tasa_otras = (otras_h / self.dur_otras) / marcha if otras_h > 0 else 0.0
        nueva_otra = lambda: float(r_otr.exponential(1 / tasa_otras)) if tasa_otras > 0 else math.inf

        t_a, t_b, t_o = nuevo(eta_a), nuevo(eta_b), nueva_otra()
        ot_pendientes = []

        for k in range(n_lotes):
            if self.env.ahora < llegadas[k]:
                yield self.env.espera(llegadas[k] - self.env.ahora)
            lote = dict(id_lote=f"{cod}-{k + 1:03d}", codigo_equipo=cod, linea=e["linea"],
                        llegada_h=float(llegadas[k]), inicio_h=self.env.ahora,
                        marcha_std_h=marchas[k], marcha_h=0.0, paradas_h=0.0, fin_h=None)
            restante = marchas[k]
            while restante > 1e-9:
                dt = min(restante, t_a, t_b, t_o)
                yield self.env.espera(dt)
                restante -= dt; t_a -= dt; t_b -= dt; t_o -= dt
                lote["marcha_h"] += dt
                if restante <= 1e-9 and min(t_a, t_b, t_o) > 1e-9:
                    break
                if t_o <= 1e-9:                          # parada no técnica
                    d = _lognormal(r_otr, self.dur_otras, 0.8)
                    t0 = self.env.ahora
                    yield self.env.espera(d)
                    self._registrar(cod, e["linea"], "no_tecnica", "Logística/auxiliares",
                                    t0, t0, 0.0, self.env.ahora, lote["id_lote"])
                    lote["paradas_h"] += d
                    t_o = nueva_otra()
                    continue
                modo = "A" if t_a <= t_b else "B"
                categoria = "Mecánica/lubricación" if modo == "A" else "Otra técnica"
                precursor = r_iot.random() < float(e["frac_precursor"])
                alerta_tardia = False
                if self._iot_activo(e) and precursor and r_iot.random() < niv["p_deteccion"]:
                    if r_iot.random() < niv["frac_anticipada"]:
                        # K6, camino 1: alerta anticipada (zona C de la curva P-F) → OT programada
                        id_al = self._nueva_alerta(cod, "anticipada")
                        ot_pendientes.append((categoria, id_al))
                        if modo == "A": t_a = nuevo(eta_a)
                        else: t_b = nuevo(eta_b)
                        continue
                    alerta_tardia = True                 # K6, camino 2: alerta en zona D
                    self._nueva_alerta(cod, "tardía")
                d = yield from self._falla(e, r_rep, categoria, lote["id_lote"], alerta_tardia)
                lote["paradas_h"] += d
                if modo == "A": t_a = nuevo(eta_a)
                else: t_b = nuevo(eta_b)
            lote["fin_h"] = self.env.ahora
            self.lotes.append(lote)
            # OT programadas por alertas anticipadas: se ejecutan con el equipo libre
            while ot_pendientes:
                cat, id_al = ot_pendientes.pop(0)
                yield from self._ot_programada(e, r_rep, cat, id_al)

    # ------------------------------------------------------------------ falla
    def _medias_mttr(self, e):
        resto = max(0.2, float(e["mttr_h"]) - self.g["respuesta_media_h"])
        espera_total = self.g["frac_espera_resto"] * resto
        reparacion = (1 - self.g["frac_espera_resto"]) * resto
        return espera_total / self.g["frac_requiere_repuesto"], reparacion

    def _falla(self, e, rng, categoria, id_lote, alerta_tardia):
        g, niv = self.g, self.niv
        t0 = self.env.ahora
        # Notificación: hoy por correo (P-MT-01); con alerta IoT se acorta
        sigma = math.sqrt(2 * math.log(g["respuesta_media_h"] / g["respuesta_mediana_h"]))
        mediana = g["respuesta_mediana_h"] * g.get("factor_notificacion", 1.0)
        notif = float(rng.lognormal(math.log(mediana), sigma))
        if alerta_tardia:
            notif *= 1 - niv["red_respuesta_alerta"]
        yield self.env.espera(notif)
        yield self.tecnicos.solicitar()
        t_atencion = self.env.ahora
        espera_media, rep_media = self._medias_mttr(e)
        espera = 0.0
        if rng.random() < g["frac_requiere_repuesto"]:
            # Situación actual: la falla espera la compra o el proveedor (fuera del alcance R2)
            espera = _lognormal(rng, espera_media, g["cv_espera"])
        if espera > 0:
            self.tecnicos.liberar()
            yield self.env.espera(espera)
            yield self.tecnicos.solicitar()
        if self._tpm_activo(e):  # K5: estandarización de la reparación
            rep_media *= 1 - niv["red_reparacion_tpm"]
        rep = _lognormal(rng, rep_media, g["cv_reparacion"])
        yield self.env.espera(rep)
        self.tecnicos.liberar()
        self.horas_tecnico += rep
        self._registrar(e["codigo"], e["linea"], "falla_tecnica", categoria, t0, t_atencion,
                        espera, self.env.ahora, id_lote)
        return self.env.ahora - t0

    def _ot_programada(self, e, rng, categoria, id_alerta=""):
        _, rep_media = self._medias_mttr(e)
        if self._tpm_activo(e):
            rep_media *= 1 - self.niv["red_reparacion_tpm"]
        yield self.tecnicos.solicitar()
        t0 = self.env.ahora
        d = _lognormal(rng, rep_media * self.g["duracion_ot_anticipada"], self.g["cv_reparacion"])
        yield self.env.espera(d)
        self.tecnicos.liberar()
        self.horas_tecnico += d
        self._registrar(e["codigo"], e["linea"], "ot_programada", categoria, t0, t0, 0.0,
                        self.env.ahora, "", id_alerta)

    # ------------------------------------------------------------------ K5: preventivo
    def _preventivo(self, cod, por_anio, tpm):
        rng = _rng(self.semilla, cod, "preventivo")
        intervalo = self.T / por_anio
        cumplimiento = self.niv.get("cumplimiento_preventivo_tobe", 1.0) if tpm \
            else self.g["cumplimiento_preventivo_asis"]
        desfase = float(rng.uniform(0.05, 0.95))   # escalonamiento entre equipos
        for k in range(por_anio):
            objetivo = (k + desfase) * intervalo
            if self.env.ahora < objetivo:
                yield self.env.espera(objetivo - self.env.ahora)
            ejecutado = rng.random() < cumplimiento
            inicio = fin = None
            if ejecutado:
                yield self.tecnicos.solicitar()
                inicio = self.env.ahora
                d = self.g["duracion_preventivo_h"]
                yield self.env.espera(d)
                self.tecnicos.liberar()
                self.horas_tecnico += d
                fin = self.env.ahora
            self.preventivos.append(dict(codigo_equipo=cod, programado_h=objetivo,
                                         ejecutado=ejecutado, tpm=tpm,
                                         inicio_ejecucion_h=inicio, fin_ejecucion_h=fin))

    # ------------------------------------------------------------------ K6: falsas alarmas
    def _falsas_alarmas(self, e):
        rng = _rng(self.semilla, e["codigo"], "falsas")
        tasa = self.niv["falsas_alarmas_mes"] / HORAS_MES
        if tasa <= 0:
            return
        while True:
            yield self.env.espera(float(rng.exponential(1 / tasa)))
            self._nueva_alerta(e["codigo"], "falsa")
            yield self.tecnicos.solicitar()
            d = self.g["duracion_falsa_alarma_h"]
            yield self.env.espera(d)
            self.tecnicos.liberar()
            self.horas_tecnico += d

    # ------------------------------------------------------------------ registro
    def _registrar(self, cod, linea, tipo, categoria, t0, t_at, espera, t_fin, id_lote,
                   id_alerta=""):
        self.eventos.append(dict(id_evento=self._nuevo_id(), codigo_equipo=cod, linea=linea,
                                 tipo=tipo, categoria=categoria, inicio_parada_h=t0,
                                 inicio_atencion_h=t_at, espera_repuesto_h=espera,
                                 fin_parada_h=t_fin, id_lote=id_lote, id_alerta=id_alerta))

    def _nueva_alerta(self, cod, tipo):
        """Registra una alerta IoT y devuelve su identificador (enlaza alerta → OT)."""
        id_al = f"AL-{len(self.alertas) + 1:04d}"
        self.alertas.append(dict(id_alerta=id_al, codigo_equipo=cod, tiempo_h=self.env.ahora,
                                 tipo=tipo))
        return id_al


def simular(parametros, escenario, semilla=1):
    return Simulacion(parametros, escenario, semilla).ejecutar()
