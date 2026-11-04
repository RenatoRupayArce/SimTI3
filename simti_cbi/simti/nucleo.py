"""Núcleo de simulación de eventos discretos (DES) basado en procesos.

Implementación mínima en Python puro, con la misma lógica de SimPy:
- Los procesos son generadores que ceden eventos (timeout, solicitud de recurso).
- Un calendario de eventos (heap) avanza el reloj al siguiente evento.
- Los recursos tienen capacidad finita y cola FIFO.
No requiere librerías externas.
"""
import heapq
import itertools


class Evento:
    __slots__ = ("env", "callbacks", "disparado", "valor")

    def __init__(self, env):
        self.env = env
        self.callbacks = []
        self.disparado = False
        self.valor = None

    def disparar(self, valor=None):
        if self.disparado:
            return
        self.disparado = True
        self.valor = valor
        self.env._agendar(0.0, self)


class Entorno:
    """Reloj y calendario de eventos. La unidad de tiempo es la hora de turno."""

    def __init__(self):
        self.ahora = 0.0
        self._cola = []
        self._contador = itertools.count()

    def _agendar(self, demora, evento):
        heapq.heappush(self._cola, (self.ahora + demora, next(self._contador), evento))

    def espera(self, demora):
        if demora < 0:
            raise ValueError(f"Demora negativa: {demora}")
        ev = Evento(self)
        ev.disparado = True
        self._agendar(demora, ev)
        return ev

    def proceso(self, generador):
        ev_inicio = Evento(self)
        ev_inicio.callbacks.append(lambda e: self._avanzar(generador, None))
        ev_inicio.disparar()
        return generador

    def _avanzar(self, generador, valor):
        try:
            evento = generador.send(valor)
        except StopIteration:
            return
        evento.callbacks.append(lambda e: self._avanzar(generador, e.valor))

    def ejecutar(self, hasta):
        while self._cola:
            t, _, ev = self._cola[0]
            if t > hasta:
                break
            heapq.heappop(self._cola)
            self.ahora = t
            for cb in ev.callbacks:
                cb(ev)
            ev.callbacks = []
        self.ahora = hasta


class Recurso:
    """Recurso con capacidad finita (técnicos) y cola FIFO."""

    def __init__(self, env, capacidad):
        self.env = env
        self.capacidad = capacidad
        self.ocupados = 0
        self.cola = []
        self.horas_ocupado = 0.0

    def solicitar(self):
        ev = Evento(self.env)
        if self.ocupados < self.capacidad:
            self.ocupados += 1
            ev.disparar()
        else:
            self.cola.append(ev)
        return ev

    def liberar(self):
        if self.cola:
            siguiente = self.cola.pop(0)
            siguiente.disparar()
        else:
            self.ocupados -= 1
