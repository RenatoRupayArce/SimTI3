# Bitácora de construcción de SimTI-CBI con apoyo de IA

Registro de todas las versiones generadas, no solo la final. Protocolo por componente:
(1) generar con IA, (2) verificar contra el criterio propio, (3) probar con datos,
(4) retroalimentar a la IA con el error preciso, (5) documentar la versión.

Asistente: Claude (Anthropic). Fecha de construcción: 11 de octubre de 2026.

| Componente | Versión | Qué se generó | Verificación y prueba con datos | Error detectado / retroalimentación | Resultado |
|---|---|---|---|---|---|
| K1 Repositorio de datos | v1 | Script `derivar_parametros.py` que arma las tablas de equipos y líneas desde las Tablas 8 y 10; reglas de calidad de datos | Cierre con los totales de planta: 112 fallas, MTBF 20,11 h, MTTR 6,20 h, 1 032,4 h de paradas | Ninguno | Aceptada |
| K2 Ajuste y calibración | v1 | Motor sin calibrar (respuesta = mediana de 72,5 min) | AS-IS de 10 réplicas: respuesta media 2,02 h (meta 1,61 h), MTTR 6,95 h (meta 6,2 h), 108,6 fallas (meta 112) | La respuesta de la línea base ya incluye la espera por el técnico; el modelo la contaba dos veces. Con horizonte finito, Weibull genera menos fallas que marcha/MTBF | Rechazada |
| K2 Ajuste y calibración | v2 | Calibración iterativa de dos factores (notificación y escala de fallas), 4 iteraciones | Respuesta 1,57 h; 112,2 fallas; factores 0,808 y 0,935 | Ninguno | Aceptada |
| K2 Ajuste y calibración | v3 | Recalibración después de corregir el motor (K4 v3) | Respuesta 1,60 h (meta 1,61 h); 112,2 fallas (meta 112); factores 0,878 y 0,935 | Ninguno | Aceptada (versión final) |
| K3 Gestor de escenarios | v1 | Diseño 2³ en orden de Yates y escenarios de sensibilidad | Las 8 combinaciones se generan con nombres y códigos correctos | En la sensibilidad del número de técnicos, el AS-IS de referencia también tomaba 2 técnicos | Corregida |
| K3 Gestor de escenarios | v2 | El AS-IS siempre usa la dotación real de la planta (1 técnico) | Comparación justa en la sensibilidad | Ninguno | Aceptada |
| K4 Motor DES | v1 | Núcleo de eventos discretos propio (Python puro) y lógica lote–falla–técnico–repuesto | Primera corrida completa: 1 464 lotes en 2 496 h de turno | Se detectó el problema de K2 v1 | Base de K2 v2 |
| K4 Motor DES | v2 | Escenarios TPM con preventivo al 100 % | Con TPM la respuesta subía de 1,59 a 1,96 h | Todas las órdenes preventivas se programaban en el mismo instante y saturaban al técnico (artefacto del modelo, no de la planta) | Rechazada |
| K4 Motor DES | v3 | Desfase aleatorio del calendario preventivo por equipo | Respuesta con TPM: 1,54 h; pruebas V01–V08 aprobadas | Ninguno | Aceptada |
| K5 Submodelo TPM y repuestos | v1 | Escala η del modo mecánico/lubricación, estandarización de la reparación, stock con cobertura | V06: con cobertura 100 % la espera es 0 h; cumplimiento del preventivo AS-IS 39,3 % (meta 38,6 %) | Ninguno | Aceptada |
| K6 Submodelo IoT | v1 | Tres caminos: alerta anticipada (OT programada), alerta tardía (respuesta reducida) y falsa alarma | Integrado: 14,2 alertas anticipadas, 4,6 tardías y 61,5 falsas por año | Ninguno | Aceptada |
| K7 KPI y valoración | v1 | KPI (ISO 22400-2, EN 15341), IC 95 %, ANOVA 2³ con bloques, valoración económica | Periodo de recuperación promediado por réplica | Si una réplica tenía beneficio negativo, el promedio daba «infinito» | Rechazada |
| K7 KPI y valoración | v2 | Periodo de recuperación calculado con el beneficio neto medio | Valores finitos y coherentes por escenario | Ninguno | Aceptada |
| K8 Aplicación Streamlit | v1 | Cinco vistas: situación actual, simulador, comparación, indicadores desde registros y validación | Prueba de humo de las cinco vistas con un sustituto de Streamlit | Las barras de progreso estaban dentro de funciones en caché | Rechazada |
| K8 Aplicación Streamlit | v2 | Barras de progreso fuera de la caché | Las cinco vistas se ejecutan sin errores | Leyendas superpuestas a las barras en dos gráficos | Corregida |
| K8 Aplicación Streamlit | v3 | Leyendas debajo de los gráficos | Revisión visual de los gráficos generados | Ninguno | Aceptada |
| K8 Aplicación Streamlit | v4 | Aviso de espera (spinner) fuera de las funciones en caché | Error en la computadora del usuario: CacheReplayClosureError en la vista 3, porque la barra de progreso se creaba fuera de la función en caché y se dibujaba desde dentro | Se eliminaron los elementos de Streamlit dentro de las funciones en caché | Aceptada |
| Pruebas | v1 | `pruebas/verificacion.py` con las pruebas V01–V08 | 8 de 8 aprobadas | Ninguno | Aceptada |
| K3 Gestor de escenarios | v3 (R2) | Se retira el factor stock: diseño 2² (TPM × IoT) | Los 4 escenarios reproducen exactamente los valores del diseño 2³ anterior (TPM + IoT: OEE 58,60 %) | Ninguno | Aceptada |
| K5 Submodelo TPM y repuestos | v2 (R2) | Sin cobertura de stock: la espera de repuesto queda como condición del AS-IS; el preventivo registra inicio y fin de ejecución | AS-IS sin cambios (8 de 8 indicadores con error ≤ 5 %) | Ninguno | Aceptada |
| K6 Submodelo IoT | v2 | Cada alerta tiene un código y la OT programada enlaza con su alerta | Prueba V06 nueva: con IoT ideal, 0 fallas con parada en equipos con sensor y todas las OT enlazadas | Ninguno | Aceptada |
| K7 KPI y valoración | v3 (R2) | ANOVA 2² con bloques y valoración sin costos de stock | ANOVA: TPM p < 0,001; IoT p < 0,001; TPM × IoT p = 0,22 | Ninguno | Aceptada |
| K1b Registros en Excel | v1 | `simti/registros.py` y `datos/generar_excel.py`: plantilla para CBI, ejemplo sintético rotulado, calendario de turnos, resúmenes TPM e IoT | Ida y vuelta del libro sin errores; plantilla vacía devuelve un mensaje claro | Al registrar una orden, la columna de observación vacía se leía como número y no aceptaba texto | Corregida |
| K8 Aplicación Streamlit | v5 (R2) | Secciones IoT, TPM (con su validación) y ficha de máquina; perfiles jefe y técnico; ayudas «?»; comprobación de eficiencia y beneficio en el simulador; sin stock | Prueba de humo de las 14 pantallas con un sustituto de Streamlit (incluidos botones y registros del técnico); revisión visual del HTML a 1280 px y 390 px | Globo de ayuda cortado en el borde izquierdo; recuadros de comprobación demasiado altos | Corregida |
| Pruebas | v2 | V06 «Caso extremo con stock infinito» se reemplaza por «Caso extremo con IoT ideal» | 8 de 8 aprobadas | Ninguno | Aceptada |

## Pendiente del equipo de tesis

- Probar la versión R2 en Streamlit Cloud y revisar las pantallas (la prueba de humo no reemplaza la revisión visual).
- Pedir a CBI el costo real por hora de parada (incluida la producción perdida): con los supuestos actuales TPM + IoT
  mejora el OEE de forma significativa, pero su beneficio neto es cercano a cero.
- Llenar la plantilla Excel con registros reales y definir con el proveedor los límites de alerta de los sensores.
- Capturar las pantallas de la versión R2 para el informe.
