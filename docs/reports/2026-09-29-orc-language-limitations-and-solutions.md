# Limitaciones de `.orc` y posibles soluciones

Fecha: 2026-09-29. Base examinada: `fc5f2a2e1426d74da4cdb79a97a494e685300141`, Workflow Lisp con destino DSL 2.33.

**Estado:** hallazgos y propuestas derivados de la comparación secuencial inspirada en MLEvolve. Este documento no modifica el contrato del lenguaje, no selecciona una arquitectura nueva y no afirma que las soluciones propuestas estén implementadas.

La búsqueda Python funciona; las formas `.orc` probadas conservan toda la política en el lenguaje, pero el controlador completo no llega a ejecutarse. La forma final genera una expresión de **361 nodos** frente al límite de **256**. También se reprodujo un fallo independiente del runtime: una llamada que no entrega un resultado nuevo puede consumir el bundle de la iteración anterior.

Evidencia principal: [informe de comparación](2026-09-29-mlevolve-orc-python-comparison.md), [controlador `.orc`](../../experiments/mlevolve_pair/search.orc), [controlador Python](../../experiments/mlevolve_pair/search.py) y [resultados registrados](../../experiments/mlevolve_pair/evidence.json). Las sondas pequeñas y el controlador completo tienen alcances distintos: una sonda que funciona no demuestra que la búsqueda completa funcione.

## 1. Resumen de los hallazgos

| Hallazgo | Clasificación | Consecuencia observada | Dirección de solución |
| --- | --- | --- | --- |
| Expresión generada de 361 nodos; máximo 256 | Límite de representación aplicado durante compilación | Rechazo de una actualización ordinaria de estado | Inspeccionar la expansión, preservar bindings y ajustar límites con evidencia |
| Llamadas con efectos y condiciones aceptadas en unas posiciones, rechazadas en otras | Defectos o huecos de composición del frontend | Reescrituras y duplicación de ramas; algunas formas producen excepciones internas | Normalización compartida de valores y efectos sobre WCC |
| Registros no admitidos como entradas del adaptador de comandos; expresiones calculadas rechazadas en argumentos | Restricción del transporte y de su lowering | Aplanar candidatos y sustituir historial completo por su longitud | Proyección tipada de valores calculados y transporte estructurado |
| Literales Float rechazados en el cuerpo, aunque los defaults Float funcionan | Asimetría de la superficie de expresiones | Introducir un input/default para expresar una constante | Extensión acotada del literal, coherente con el evaluador existente |
| Bundle anterior aceptado cuando falta el actual | Defecto de entrega de resultados del runtime | La ejecución termina correctamente con datos que no produjo la segunda llamada | Identidad y ruta por invocación; exigir un resultado nuevo antes del commit |
| Sin mapa general de comandos concurrentes | Capacidad no disponible en la superficie examinada | `list/map-effect` no sustituye un executor concurrente | Considerarlo aparte, solo si hay un consumidor que lo necesite |

No todos estos puntos son carencias deliberadas del lenguaje. Los errores internos del compilador y la aceptación de resultados antiguos son defectos. El conjunto cerrado de operadores y el recorrido secuencial son restricciones documentadas. La distinción importa al decidir entre reparar una implementación y ampliar un contrato.

## 2. Tamaño de las expresiones generadas

### Evidencia

El controlador lleva dos incumbentes, sus evaluaciones, el mejor resultado, reparación pendiente, contadores y `List[Trial]`. Incluso la forma con ramas explícitas y `continue` en cada salida falla en el `record-update` de reparación A:

```text
pure_expr_payload_too_large
pure-expression payload exceeds the maximum node count
node_count: 361
max_nodes: 256
```

La CLI publica el código de error y la ubicación; **no publica esos dos contadores**. Se obtuvieron imprimiendo los metadatos de `_raise` mediante un wrapper observacional que conservaba la excepción original. El límite y la comprobación están en [pure_expr.py](../../orchestrator/workflow/pure_expr.py), en `DEFAULT_PURE_EXPR_MAX_NODES` y `validate_pure_expr_payload`.

El límite se aplica al árbol de expresión generado, no al número de líneas `.orc`, iteraciones o candidatos. Dividir texto entre helpers o introducir `let*` no garantizó una representación más pequeña. La forma compacta también alcanzó el límite en expresiones de selección.

### Posibles soluciones

1. **Hacer observable la expansión.** Incluir tamaño, límite y origen en el diagnóstico estructurado. Mostrar qué subexpresiones dominan el payload permitiría distinguir duplicación causada por lowering de una expresión realmente grande. El conteo 361, por sí solo, no demuestra una causa única.
2. **Preservar bindings y compartir valores.** Aprovechar los bindings léxicos que ya existen en el esquema 3 de expresiones y en WCC, evitando sustituir repetidamente el árbol completo de un valor. No hace falta inventar otro lenguaje de expresiones ni otro evaluador. Debe verificarse que la representación resultante conserva ámbito, orden, tipos y comportamiento de reanudación.
3. **Particionar regiones puras cuando sea necesario.** Si una región legítima sigue siendo grande, estudiar su división en unidades con dependencias explícitas. Esto puede aumentar pasos, persistencia y trabajo de replay; debe compararse con conservar valores como expresiones. No introducir comandos ficticios para forzar una frontera.
4. **Evaluar un límite mayor como experimento acotado.** Elevarlo temporalmente, por ejemplo a 512, permitiría comprobar si aparece otro bloqueo. No se hizo en esta investigación. Superar ese primer error no demostraría que la búsqueda ejecuta correctamente ni que aumentar el límite sea una solución suficiente.

**Criterio de aceptación:** compilar y ejecutar el controlador, igualar la traza y el presupuesto Python, comprobar crecimiento de tamaño al ampliar estado/ramas y verificar recuperación. Un simple cambio de constante que permita compilar no basta.

## 3. Composición dependiente de la posición

### Evidencia

| Forma intentada | Resultado observado |
| --- | --- |
| `(continue (advance-search state))`, con helper que realiza efectos | Excepción WCC por `ProcedureCallExpr` |
| Ligar el helper antes de `continue` | Superó esa colocación; apareció el límite de tamaño |
| Ramas explícitas dentro del helper | `ValueError: pure boolean conditions require WCC pure-projection lowering` |
| Ligar a `next-state` un condicional que contiene comandos | `workflow_return_not_exportable`: `let*` binding `LetStarExpr` no soportado |
| Ramas explícitas directamente en el bucle, cada una terminando en `continue` | Superó esas restricciones; volvió a aparecer el límite de tamaño |

Los mensajes se originan en [elaborate.py](../../orchestrator/workflow_lisp/wcc/elaborate.py), [conditionals.py](../../orchestrator/workflow_lisp/conditionals.py) y [lowering/core.py](../../orchestrator/workflow_lisp/lowering/core.py). El informe principal conserva la secuencia de intentos; el archivo final conserva la última forma, no todas las variantes intermedias.

### Solución de autoría disponible

Ligar una llamada antes de consumirla, o colocar la continuación en las ramas terminales, resolvió errores concretos. Es una alternativa local que puede permitir avanzar. No demuestra composición general y, en este caso, no logró un controlador ejecutable. La duplicación de ramas tampoco debería convertirse en el diseño recomendado de una biblioteca de búsqueda.

### Solución del compilador

Normalizar los operandos mediante el mecanismo compartido de WCC: secuenciar los efectos, ligar sus resultados y construir el valor que consume la continuación. Reutilizar el trabajo existente de normalización, inferencia de efectos y bindings; evitar una excepción distinta para cada combinación de helper, campo, argumento y rama.

Las llamadas admitidas deben conservar orden, identidad de invocación, alcance de variables y correspondencia con el código fuente. Las formas deliberadamente excluidas deben producir diagnósticos estables. Sustituir una excepción interna por un mensaje mejor es útil, pero no resuelve la falta de composición.

La [composición de llamadas puras](../design/workflow_lisp_pure_call_composition.md) ya implementa un subconjunto desde 2.30. No debe confundirse con permiso general para colocar llamadas con efectos en cualquier expresión.

**Criterio de aceptación:** probar las mismas operaciones en binding, continuación y ramas, tanto directamente como mediante helpers locales/importados, y comparar efectos ordenados, resultado y reanudación. Las pruebas deben comprobar comportamiento, no el texto literal de prompts o diagnósticos.

## 4. Frontera entre valores tipados y comandos

### Evidencia

Pasar un registro calculado completo por `:argv` fue rechazado con `workflow_return_not_exportable`. Pasarlo por `command-result :adapter ... :inputs` produjo `command_adapter_input_not_projectable`. La comprobación actual está en `_validate_adapter_input_projectable`, en [typecheck_effects.py](../../orchestrator/workflow_lisp/typecheck_effects.py).

También se rechazó `(list/length state.history)` directamente como argumento. El controlador final usa `state.evaluations`: es equivalente en esta fixture porque cada evaluación añade exactamente un trial. Esa equivalencia no es una regla general para cualquier historial.

La solución de autoría fue pasar coeficientes escalares y longitud de historial. El historial completo sigue siendo estado `.orc`; no se trasladó a un controlador Python. Sin embargo, la hoja de propuestas ya no recibe todos los trials y no demuestra recuperación semántica de experiencias.

### Posibles soluciones

- **Proyectar expresiones admitidas antes de construir el argumento.** El mismo valor tipado debería poder consumirse en una llamada sin exigir que el autor encuentre un nombre equivalente o un lugar especial donde calcularlo.
- **Extender el protocolo JSON tipado a registros y listas transportables.** El protocolo existente ya construye un objeto JSON para el adaptador. Estudiar soporte recursivo a partir del contrato declarado, con validación, serialización determinista y límites de tamaño. Conservar las distinciones de tipos y las reglas de paths; no convertir todo en cadenas sin contrato.
- **Usar vistas materializadas para datos grandes.** La superficie existente `materialize-view` puede ser el punto de partida para entregar un artefacto declarado al evaluador o proveedor. Su combinación exacta con este historial y estos comandos no se probó. Un archivo que representa datos no debe convertirse en un almacén paralelo que decide el estado de búsqueda.

Para candidatos que ya son programas o artefactos, pasar un path puede ser la API natural. Para registros pequeños, exigir un archivo adicional puede añadir ceremonia sin aportar valor.

**Criterio de aceptación:** transportar un candidato y una lista de trials con tipos preservados; rechazar datos incompatibles; comprobar que ambas implementaciones reciben los mismos datos. La hoja externa no debe seleccionar rama, ganador, presupuesto o continuación.

## 5. Float y cálculo numérico

Una sonda rechazó un literal como `:best 999.0` en una expresión con `frontend_parse_error`; un parámetro público `(initial Float :default 999.0)` funcionó. Comparar scores Float producidos por comandos también funcionó.

La solución local es usar un score calculado o un parámetro tipado existente. Añadir parámetros públicos solo para expresar constantes internas es un coste de autoría, no una buena interfaz por defecto.

La posible reparación es admitir el literal Float en la superficie de expresiones correspondiente, reutilizando su representación, validación de valores finitos y semántica de evaluación. Deben comprobarse compilación constante, ejecución y serialización, sin introducir conversiones silenciosas entre tipos.

Separadamente, el [contrato de expresiones](../design/workflow_lisp_frontend_specification.md) admite ordenación Float pero limita la aritmética indicada a Int y excluye división. No se implementó UCT ni se probó una selección numérica equivalente. Si una política requiere operaciones adicionales, habría que justificar una extensión numérica pequeña y coherente; externalizar la selección completa en Python ocultaría justamente la política que se quiere expresar en `.orc`.

Entrenamiento, métricas y otras operaciones de una biblioteca ML sí pueden justificar una frontera Python. La suma de cuadrados de esta fixture no requiere intrínsecamente Python: se eligió como sustituto controlado de un experimento externo.

## 6. El resultado debe pertenecer a la llamada actual

### Evidencia

La [sonda de bundle ausente](../../experiments/mlevolve_pair/probes/missing_bundle.orc) llama dos veces al mismo comando. La primera llamada escribe `{"ordinal": 0}`; la segunda termina con éxito sin escribir nada. El runtime termina con:

```json
{"return__round": 2, "return__history": [{"ordinal": 0}, {"ordinal": 0}]}
```

En cambio, la [sonda de tipo incorrecto](../../experiments/mlevolve_pair/probes/malformed_result.orc) es rechazada correctamente. Por tanto, el problema no es que falte toda validación: un resultado antiguo puede satisfacer el esquema del resultado esperado.

### Solución propuesta

Dar a cada invocación una identidad y una ruta de resultado propias; exigir ausencia antes de iniciarla y presencia de una entrega válida antes de comprometerla. La identidad debe distinguir activaciones del bucle e intentos. La [decisión existente sobre valores y efectos](2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md#7-changes-that-do-not-depend-on-the-option) ya contempla rutas que identifican llamadas y ausencia previa.

La reanudación debe reutilizar un resultado **comprometido e identificado**, no cualquier archivo presente en un path. No borrar indiscriminadamente evidencia válida de un intento anterior. Un archivo nuevo tampoco garantiza por sí solo atomicidad: hay que definir qué ocurre si el proceso muere durante escritura, después del efecto externo o antes del commit.

Comprobar únicamente el mtime no establece la identidad de la entrega. Vaciar o borrar el archivo antes de llamar podría reducir este caso local, pero necesita una política de intentos y recuperación para ser una reparación completa.

**Criterio de aceptación:** salida ausente, salida mal formada, dos iteraciones, reintento y reanudación tras commit. Un resultado válido anterior nunca debe convertir en éxito una llamada que omitió su salida. Recuperar desde un límite comprometido no equivale a garantizar exactamente una ejecución de un efecto externo arbitrario.

## 7. Concurrencia: un requisito separado

La comparación solicitada es secuencial. `list/map-effect` conserva ejecución ordenada; `trial` ofrece brazos estáticos con contratos de runs y evaluación, no un mapa general de comandos dinámicos. Los grupos de proveedores tampoco son un pool genérico de evaluadores numéricos.

Si aparece esa necesidad, estudiar una operación acotada sobre una instantánea de candidatos, con límite de concurrencia, identidad por tarea, orden definido de resultados, contabilidad de presupuesto y política de fallo/cancelación. Seleccionar el segundo candidato antes de observar el resultado del primero cambia la política; no es una optimización transparente de este experimento.

No se propone añadir concurrencia para resolver los fallos secuenciales. Tampoco esconder un scheduler específico de búsqueda dentro de una hoja Python.

## 8. Cómo encajan las soluciones

La [decisión de separación de valores y efectos](2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md#12-decisions) ya registra reparaciones aprobadas y un spike posterior. Mantiene abierta la elección arquitectónica. Este informe aporta un caso adicional de búsqueda y no reemplaza esa decisión.

| Alternativa existente | Qué podría aportar | Coste o límite |
| --- | --- | --- |
| A. Reparar la ruta que compila a pasos | Corregir normalización y las formas rechazadas conservando el runtime actual | Hay que demostrar que las correcciones cubren las posiciones admitidas, sin multiplicar lowerers especiales |
| B. Mantener pasos para efectos y valores como expresiones | Expresar dependencias de datos sin exigir una fila persistida para cada valor puro | Cambia representación, evaluación y replay; no elimina por sí sola un límite de tamaño mal calibrado |
| C. Ejecutar WCC con entorno léxico y memo de efectos | Hacer más uniforme la composición de llamadas, ramas y valores | Cambio mayor de ejecución, identidad, estado y recuperación; su beneficio requiere el spike y evidencia de paridad |

La evidencia no permite afirmar que una inversión del runtime sea imprescindible ni que elevar 256 a 512 arregle el sistema. La reparación de entrega de resultados es necesaria con cualquiera de esas arquitecturas.

Orden recomendado para evaluar soluciones, sin cambiar el roadmap: reparar frescura e informar mejor los errores; usar este controlador como caso de composición y tamaño; extender el transporte de datos que requiera un consumidor; resolver la asimetría de literales. Mantener aritmética adicional y concurrencia como necesidades explícitas, no como requisitos de esta comparación.

Lo que este enfoque deja pendiente es determinar el coste de la arquitectura elegida y su comportamiento con historiales grandes. La prueba que cerraría la cuestión inmediata es ejecutar el mismo controlador secuencial, igualar sus decisiones y presupuesto con Python y reanudarlo desde un commit sin repetir evaluaciones comprometidas.

## 9. Reproducción y límites de la evidencia

Desde la raíz del worktree de la investigación:

```bash
python -m experiments.mlevolve_pair.compare --output /tmp/mlevolve-pair-evidence.json

python -m orchestrator run experiments/mlevolve_pair/search.orc \
  --command-boundaries-file experiments/mlevolve_pair/commands.json \
  --state-dir /tmp/mlevolve-direct-branches --quiet

python -m orchestrator run experiments/mlevolve_pair/probes/missing_bundle.orc \
  --command-boundaries-file experiments/mlevolve_pair/probes/commands.json \
  --state-dir /tmp/mlevolve-missing-result --quiet
```

En la base examinada, el harness registra igualdad entre los transportes Python y `compile_failed` para ORC. Que el harness termine con código 0 significa que produjo el informe sin discrepancias Python; no significa que ORC compiló. El segundo comando termina con código 2. El tercero reproduce la aceptación del resultado anterior.

Las listas de registros en estado de bucle sí están implementadas desde 2.29; una sonda pequeña conservó historial y comparó scores. No debe presentarse esa capacidad como ausente. Las seis pruebas del espécimen Python pasaron y las pruebas existentes de reanudación de bucles ricos pasaron en la investigación. Ninguna demuestra ejecución, rendimiento o recuperación del controlador ORC completo.

Las propuestas de este documento no se ejecutaron ni se incorporaron al compilador/runtime. Antes de implementarlas, sus contratos deben concretarse en los documentos propietarios enlazados desde [docs/index.md](../index.md).
