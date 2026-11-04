# Manual de usuario — SimTI-CBI · R2 TPM + IoT

SimTI-CBI responde una pregunta: **¿cuánto mejora el OEE de CBI Perú si se implementan las prácticas TPM y el
monitoreo IoT, y cuánto cuesta?** Además, permite **monitorear** las máquinas con sensores (IoT), **gestionar**
el mantenimiento (TPM) y **calcular** los indicadores (OEE, MTBF, MTTR) a partir de los registros de la planta.

> Alcance R2: TPM + IoT. El stock de repuestos no forma parte de la solución. La espera de repuestos se mantiene
> en el modelo porque es parte de la situación actual de la planta.

## 1. Instalación (una sola vez)

1. Instale Python 3.10 o superior desde python.org (marque «Add Python to PATH»).
2. Abra una terminal en la carpeta `simti_cbi`.
3. Ejecute: `pip install -r requirements.txt`

## 2. Abrir la aplicación

```
streamlit run app.py
```

Se abre el navegador en `http://localhost:8501`. La primera vez la aplicación calibra el modelo (unos segundos).
En Streamlit Cloud basta con subir esta carpeta al repositorio de GitHub conectado a la app.

## 3. Perfiles

En la barra lateral, **Perfil** cambia la interfaz (no es un inicio de sesión):

| Perfil | Ve |
|---|---|
| **Jefe de mantenimiento** | Inicio, IoT, TPM (con su validación), ficha de máquina, indicadores, situación actual, simulador, comparación y validación del modelo |
| **Técnico de mantenimiento** | Mis órdenes de trabajo, checklist de mantenimiento autónomo, alertas de las máquinas, ficha de máquina y guía de sensores |

Las órdenes que registra el técnico se ven de inmediato en las pantallas del jefe durante la misma sesión.
Para conservarlas, use **⬇ Descargar libro actualizado** y vuelva a subir ese Excel: la aplicación no guarda
cambios en el servidor.

## 4. Datos de planta: el libro Excel

| Fuente | Uso |
|---|---|
| **Ejemplo sintético** | Libro `datos/ejemplo_sintetico_CBI.xlsx`, generado con el simulador (escenario TPM + IoT, 2024). Sirve para probar la herramienta. Se muestra con una franja amarilla «Datos sintéticos». |
| **Excel de CBI** | El libro que llena la empresa con la plantilla `datos/plantilla_registros_CBI.xlsx` (botón en la barra lateral). |

Hojas del libro (la hoja *LEEME* explica cada columna):

| Hoja | Obligatoria | Para qué |
|---|---|---|
| Configuracion | — | Turno (hora de inicio, horas, días), fecha de corte y si los datos son reales o sintéticos |
| Equipos | — | Equipos, clase A y si tienen sensor |
| Paradas | Sí | Fallas técnicas y paradas no técnicas → disponibilidad, MTBF, MTTR |
| Lotes | Sí | Horas de marcha por lote → disponibilidad y OEE |
| Preventivos | Para TPM | Plan preventivo, OT por alerta IoT y mantenimiento autónomo; estado realizada/vencida/pendiente |
| Sensores | Para IoT | Sensores por equipo y su límite de alerta |
| Lecturas_IoT | Para IoT | Lecturas exportadas de la plataforma de sensores |
| Alertas_IoT | Para IoT | Alertas (anticipada, tardía, falsa) y su resultado |

Las fechas se convierten a «horas de turno» con el calendario de *Configuracion*. La aplicación **no se conecta
a sensores físicos**: el estado de transmisión se infiere de la fecha de la última lectura registrada.

## 5. Secciones del jefe

**Inicio.** Flujo de la solución (sensor → alerta → OT TPM → mantenimiento → indicadores) y estado de los datos.

**IoT · Monitoreo de máquinas.** Tarjeta por máquina con sus sensores (última lectura / límite), estado,
alertas y OT generadas; tendencias de cada sensor; tabla alerta → OT TPM; guía de qué mide cada sensor.

**TPM · Gestión del mantenimiento.** Cumplimiento del plan, órdenes realizadas, vencidas y pendientes, OT
originadas por IoT; tabla por máquina con disponibilidad, MTBF y MTTR; lista de actividades con filtros; pestaña
**Validación de TPM**.

**Ficha de máquina · IoT + TPM.** En una pantalla: sensores, órdenes, indicadores, tendencias y el historial
alerta → OT → falla de un equipo.

**Indicadores desde registros.** OEE, disponibilidad, MTBF, MTTR, Pareto y ajuste Weibull por equipo.

**Situación actual (AS-IS).** La planta de hoy reproducida por el modelo calibrado.

**Simulador de escenarios.** Active A · TPM (con el cumplimiento del plan preventivo) y B · IoT (con los equipos
con sensor), presione **Simular** y lea la **comprobación**: (1) ¿mejora la eficiencia (OEE)?, con prueba t pareada
frente al AS-IS; (2) ¿tiene beneficio económico?, con el costo por hora de parada a partir del cual el beneficio es
positivo y a partir del cual la inversión se recupera en 12 meses.

**Comparación y decisión.** Las 4 combinaciones del diseño 2² (AS-IS, solo TPM, solo IoT, TPM + IoT) con la
comprobación de TPM + IoT.

**Validación del modelo.** AS-IS frente a la línea base, pruebas V01–V08, ANOVA 2², interacción TPM × IoT y
análisis de sensibilidad.

## 6. ¿Cómo se valida TPM?

Pestaña *TPM → Validación de TPM*. Cada indicador registrado (cumplimiento del plan en clase A, MTBF, MTTR,
disponibilidad, paradas anualizadas y OEE) se compara con:

1. la **línea base** del diagnóstico (debe mejorar), y
2. lo que el **modelo** predijo para TPM + IoT (debe alcanzarlo con un margen de 5 %).

En el modelo, el ANOVA del diseño 2² confirma que el efecto de TPM sobre el OEE es significativo.
Con el ejemplo sintético la tabla solo demuestra el procedimiento; la validación real se hace con datos de CBI.

## 7. Secciones del técnico

**Mis órdenes de trabajo.** Órdenes de los próximos 7 días y vencidas. Marque «Hecha», ponga la fecha y una
observación, y presione *Registrar*. Escriba su nombre en la barra lateral.

**Checklist de mantenimiento autónomo.** Inspección diaria (limpieza, inspección, lubricación, ajuste, seguridad).
Si describe una anomalía, se crea una OT pendiente.

**Alertas de las máquinas.** Sensores fuera de límite y alertas de la última semana, con qué revisar.

**¿Qué miden los sensores?** Vibración (mm/s), temperatura (°C) y corriente (A): qué mide cada uno, dónde se
instala, qué falla anticipa y qué revisar.

## 8. Sin interfaz

`python ejecutar_experimento.py 30` corre todo con 30 réplicas y guarda tablas y figuras en `resultados/`.
`python pruebas/verificacion.py` ejecuta las pruebas de verificación.
`python datos/generar_excel.py` regenera la plantilla y el ejemplo sintético.

## 9. Cómo actualizar los parámetros del modelo

- Equipos y líneas: `datos/parametros_equipos.csv` y `datos/parametros_lineas.csv` (o `datos/derivar_parametros.py`).
- Parámetros de mejora: `datos/parametros_escenario.csv` (pesimista, base, optimista y fuente).
- Costos: `datos/parametros_economicos.csv` o la barra lateral. El **costo por hora de parada** debe incluir la
  producción que se deja de vender: es el dato que más influye en el beneficio.
