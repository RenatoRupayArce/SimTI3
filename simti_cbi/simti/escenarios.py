"""K3 · Gestor de escenarios: factorial 2² (TPM × IoT) y sensibilidad.

R2 (v2): el factor stock de repuestos se retiró del alcance de la solución.
La espera de repuestos sigue siendo parte de la situación actual de la planta.
"""
from dataclasses import dataclass, field, replace
from itertools import product


@dataclass
class Escenario:
    nombre: str
    tpm: bool = False          # Factor A: prácticas TPM (K5)
    iot: bool = False          # Factor B: monitoreo IoT (K6)
    niveles: dict = field(default_factory=dict)   # parámetros δ y supuestos
    n_tecnicos: int = 1
    equipos_sensor: tuple = ()  # vacío = candidatos de la tabla de equipos

    def codigo(self):
        return ("A" if self.tpm else "-") + ("B" if self.iot else "-")


CODIGO_ASIS = "--"

NOMBRES = {
    (False, False): "AS-IS",
    (True, False): "Solo TPM",
    (False, True): "Solo IoT",
    (True, True): "TPM + IoT (R2)",
}


def diseno_factorial(niveles, n_tecnicos=1):
    """Las 4 combinaciones del diseño 2², en orden estándar de Yates."""
    escenarios = []
    for b, a in product([False, True], repeat=2):
        escenarios.append(Escenario(NOMBRES[(a, b)], tpm=a, iot=b,
                                    niveles=dict(niveles), n_tecnicos=n_tecnicos))
    return escenarios


def escenarios_sensibilidad(tabla_escenario, base_niveles, n_tecnicos=1):
    """Un escenario TPM + IoT por cada parámetro en su nivel pesimista y optimista."""
    integrado = Escenario(NOMBRES[(True, True)], True, True, dict(base_niveles), n_tecnicos)
    salida = []
    for r in tabla_escenario.itertuples():
        if r.pesimista == r.optimista:
            continue
        for etiqueta in ("pesimista", "optimista"):
            niv = dict(base_niveles)
            niv[r.parametro] = float(getattr(r, etiqueta))
            salida.append((r.parametro, etiqueta, replace(integrado, niveles=niv)))
    for etiqueta, n in (("pesimista", max(1, n_tecnicos)), ("optimista", n_tecnicos + 1)):
        salida.append(("n_tecnicos", etiqueta, replace(integrado, n_tecnicos=n)))
    return integrado, salida
