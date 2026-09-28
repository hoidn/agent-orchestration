# Revisión de Composition-First Procedures y CF-1

- **Fecha:** 2026-09-28.
- **Tipo y autoridad:** informe de revisión; evidencia y recomendaciones, no
  contrato normativo, aprobación de implementación ni selección de trabajo.
- **Objeto:** [Composition-First Procedures](../design/workflow_lisp_composition_first.md)
  y [CF-1 en la hoja de ruta](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected).
- **Base revisada:** `ca0a1be3`. Al guardar este informe, HEAD era
  `dd7a88c0fdeee02b1ac8c7d26e420cc300344b3e`; los documentos y fuentes citados
  para los hallazgos no habían cambiado entre ambas revisiones.
- **Uso:** recomendaciones para corregir el diseño antes del plan. Las firmas
  propuestas no son sintaxis implementada ni ejemplos copiables. Para el
  lenguaje disponible, consultar la [matriz de capacidades](../capability_status_matrix.md)
  y la [guía de autoría](../lisp_workflow_drafting_guide.md).

## Dictamen

La dirección es acertada, pero el contrato necesita correcciones antes de
aprobar un plan de implementación. No se identificó un fallo conceptual que
justifique abandonar el enfoque o reescribir el runtime.

Conviene conservar:

- Procedimientos que devuelven el valor producido junto al resultado de dominio.
- Uniones genéricas resueltas durante compilación y un helper ordinario de
  biblioteca, sin un nuevo motor específico de revisión.
- La semántica explícita de `EXHAUSTED`: último candidato disponible, que puede
  ser una revisión final aún no evaluada, sin presentarlo como aprobado.
- EL-1 independiente, herramientas delegadas a proveedores/agentes y ausencia
  de nuevos sistemas universales de historial, snapshots o presupuestos.
- Separación entre mecanismo funcional y evidencia de utilidad real.

La revisión contó con una segunda lectura independiente de Sol; el coordinador
comprobó las fuentes y ejecutó las verificaciones descritas al final.

## Hallazgos que deben resolverse antes del plan

### 1. La migración pura no conserva la validación existente

**Prioridad: alta. Clasificación: `semantic_conflict`.**

Las secciones «Boundaries», «Effects» y «Migration» proponen validación en la
frontera del proveedor, conversión pura y hooks intactos. Sin embargo, el
contrato `ReviewFindings` sólo declara un `String` y una ruta. El
[validador existente](../../orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py),
en `main`, comprueba además que `schema_version` sea `ReviewFindings.v1` y
que el JSON referenciado sea un objeto con un miembro `items`.

Estas comprobaciones no son equivalentes a validar el tipo del resultado del
proveedor. Un adaptador puro no puede leer ese archivo. La
[integración de review/revise, sección 14.1](../design/workflow_lisp_review_revise_stdlib_parametric_integration.md)
también exige validación antes de publicar findings y antes de que `fix` los
consuma tras una reanudación.

**Corrección recomendada:** mantener `improve` libre del validador específico
de documentos, pero asignar explícitamente esas obligaciones a un adaptador
de dominio con efectos, o a una frontera productora con validación equivalente.
Precisar la conservación del contrato tras resume. Esto preserva el significado
de los datos; no introduce un eje de evaluación de seguridad de ejecución.

### 2. Los adaptadores descritos no bastan para conservar los resultados

**Prioridad: alta. Clasificación: `semantic_conflict`.**

La migración propone `Decision[ReviewEvidence BlockerClass]` con hooks intactos.
En [review_revise_design_docs.orc](../../workflows/examples/review_revise_design_docs.orc):

- `fix-design-doc` recibe `ReviewFindings`, mientras `improve` exige que
  `revise` reciba `F`, aquí `ReviewEvidence`. Bajo la invariancia de `ProcRef`,
  no es una sustitución directa.
- La rama `BLOCKED` publica un informe y findings además de la clase de bloqueo.
  Usar solamente `BlockerClass` como `B` pierde esos datos.
- La rama `EXHAUSTED` consume el último informe y findings. El nuevo resultado
  los omite deliberadamente; trasladarlos a `S` requiere describir su estado
  inicial y los adaptadores necesarios, no prometer conservación automática.

**Corrección recomendada:** definir los registros de evidencia y bloqueo del
dominio, adaptar tanto `review` como `revise`, y declarar qué resultados públicos
se conservan y cuáles cambian. El adaptador de `revise` puede extraer `.findings`
para invocar el fixer existente. No añadir historial universal al helper para
resolver necesidades particulares de estos consumidores.

### 3. El segundo ejemplo no tiene los hooks que se promete conservar

**Prioridad: media. Clasificación: `stale_duplicate`.**

[review_revise_parametric_design_docs.orc](../../workflows/examples/review_revise_parametric_design_docs.orc)
todavía usa `:review-provider`, `:fix-provider`, prompts y `:returns`; no define
los procedimientos review/fix que presupone la migración. Su prueba
`test_review_revise_parametric_design_docs_example_remains_one_off_source_shape`
en [test_workflow_lisp_examples.py](../../tests/test_workflow_lisp_examples.py)
comprueba contenido histórico, no compilación ni ejecución.

**Corrección recomendada:** seleccionar otro consumidor mantenido con hooks
reales, o incluir explícitamente esta conversión adicional. No contabilizarlo
como una migración de hooks intactos ni usar su prueba textual como evidencia
de viabilidad.

### 4. La primera entrega y sus prerrequisitos son ambiguos

**Prioridad: media. Clasificación: `semantic_conflict` y `over_specific_instruction`.**

La sección de factibilidad permite diferir los resultados genéricos de
`defprompt` mediante adaptadores, pero CF-1b exige implementar aplicaciones
genéricas también en resultados de prompts. Son criterios de cierre distintos.

Además, CF-1a y la sección de factibilidad pueden leerse como una exigencia de
demostrar ejecutablemente las nuevas uniones genéricas antes de aceptar el plan
que las implementaría. Registrar una brecha es válido; no debería convertirse
en una obligación de implementar la capacidad antes de planificarla.

**Corrección recomendada:** distinguir comprobaciones de capacidades existentes,
decisiones de contrato para capacidades nuevas y pruebas de aceptación de su
implementación. Elegir explícitamente una ruta de prompts para la primera
entrega y reflejar la misma salida aceptable en diseño y roadmap.

### 5. El delta genérico requiere reglas algo más precisas

**Prioridad: media. Tipo: precisión de contrato y factibilidad.**

La afirmación de que sólo hace falta aplicación de tipos subestima una extensión
concreta. `_infer_parametric_type_bindings`, en
[procedure_typecheck.py](../../orchestrator/workflow_lisp/procedure_typecheck.py),
recorre firmas de `ProcRef`, colecciones y un caso contextual específico, pero
no dispone de una regla general para aplicaciones de constructores nominales.

Además, `type_refs_compatible`, en
[type_env.py](../../orchestrator/workflow_lisp/type_env.py), puede aceptar uniones
por nombre corto y estructura. El diseño promete distinguir declaraciones de
módulos diferentes: esa garantía no debe darse por heredada.

**Corrección recomendada:** incorporar al
[diseño del sistema de tipos](../design/workflow_lisp_parametric_type_system.md)
reglas breves para inferir argumentos dentro de `Decision[F B]`, preservar la
identidad del constructor y sus argumentos, y diagnosticar conflictos en el
caller. Cubrir alias importados y constructores homónimos; si se admiten
parámetros no usados en payloads, conservar también su identidad. Implementar
esto en el mecanismo existente, no en una vía especial para review/revise.

### 6. La retirada propuesta abarca demasiado

**Prioridad: media. Clasificación: `over_specific_instruction`.**

La sección «Migration» y CF-1c hablan de eliminar `std/phase` cuando migren ocho
callers. Pero [std/phase.orc](../../orchestrator/workflow_lisp/stdlib_modules/std/phase.orc)
también exporta `with-phase`, `phase-scope` y tipos con consumidores
independientes. Por ejemplo,
[with_phase_composed_binding.orc](../../workflows/examples/with_phase_composed_binding.orc)
importa `with-phase`, y el
[panel de revisión](../../workflows/examples/review_revise_design_docs_judgment_panel.orc)
importa `ReviewReportPath`.

**Corrección recomendada:** inventariar consumidores por declaración y retirar
sólo el helper y la macro de review/revise desplazados. Conservar las superficies
independientes; migrar importadores de un módulo no equivale a sustituir todas
sus responsabilidades.

## Ajustes de ergonomía

### 7. No justificar estado adicional con una limitación inexistente

La sección «Loop and termination» afirma que el cuerpo no accede a bindings
exteriores. Sin embargo, `typecheck_loop_recur_expr`, en
[typecheck_loop_recur.py](../../orchestrator/workflow_lisp/typecheck_loop_recur.py),
conserva el entorno exterior. El
[fixture genérico importado](../../tests/fixtures/workflow_lisp/modules/valid/generic_loop_union_cross_module/generic_loop_union_cross_module/helper.orc)
usa `(selector ctx)` sin llevar `ctx` en el estado, y su prueba de compilación
pasó durante esta revisión.

Corregir la afirmación. Transportar `inputs` en el estado puede ser una elección
explícita, pero no una necesidad demostrada por esa premisa. Verificar el caso
concreto de captura y resume antes de decidir su representación.

### 8. Justificar o retirar las restricciones `is-record`

El algoritmo no inspecciona campos de `S` ni de `I`. Exigir registros excluye
sujetos unión y entradas escalares que podrían ser transportables, y puede
forzar envoltorios sin utilidad para el usuario.

Aceptar los valores que soporten las fronteras necesarias, o documentar la
limitación concreta de la primera entrega y su motivo. No ampliar a todos los
tipos sin verificación, pero tampoco convertir una restricción heredada en un
principio permanente del lenguaje.

## Siguiente paso recomendado

Corregir los contratos anteriores y preparar un plan pequeño centrado en un
candidato estructurado que cambia, atraviesa el helper y llega por valor a un
consumidor determinista. Después, sustituir el reviewer por dos revisiones
secuenciales más adjudicación sin modificar el caller. Ambas comprobaciones
ya están contempladas por el diseño: conviene mantenerlas como centro, no
añadir otro framework o harness.

Los ejemplos basados sólo en rutas mutables sirven para comprobar compatibilidad,
pero no bastan para demostrar composición de valores. Registrar el trabajo real
de adaptación y cualquier filtración de detalles de ejecución, sin convertirlo
en una puntuación artificial de productividad.

El resultado puede apoyar composición y reutilización. Valores e identidades
visibles pueden ayudar a la introspección; hooks sustituibles pueden facilitar
autoprogramación y búsqueda futura. Ninguna de estas últimas ventajas queda
demostrada sólo porque el helper compile o sus regresiones pasen.

## Verificación realizada durante la revisión

Esta sección registra las comprobaciones de la revisión original, anteriores
a las enmiendas documentales descritas en el seguimiento al final.

Desde la raíz del repositorio se ejecutaron estas pruebas existentes:

```bash
python -m pytest -q \
  tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_validates_with_parameterized_context_docs \
  tests/test_workflow_lisp_examples.py::test_review_revise_parametric_design_docs_example_remains_one_off_source_shape

python -m pytest -q \
  tests/test_workflow_lisp_generic_stdlib_composition.py::test_cross_module_generic_loop_projects_caller_union_fields \
  tests/test_workflow_lisp_generic_stdlib_composition.py::test_same_module_generic_loop_projects_caller_union_fields

python -m orchestrator compile \
  workflows/examples/review_revise_design_docs.orc \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json
```

Resultados: dos pruebas aprobadas en cada invocación de pytest; compilación
pública con salida 0, cero diagnósticos y ruta WCC/schema-2. La prueba histórica
de forma fuente conserva exactamente ese alcance limitado.

No se ejecutó la suite completa, no se llamaron proveedores y no se implementó
ninguna capacidad nueva. Estas comprobaciones respaldan premisas de la revisión;
no prueban todavía uniones genéricas, la migración propuesta ni su utilidad.
Este informe registra hallazgos: no los declara corregidos ni modifica el
diseño, la hoja de ruta o la selección de trabajo.

## Seguimiento: enmiendas documentales

El usuario solicitó aplicar las recomendaciones. El
[plan de enmiendas](../plans/2026-09-28-composition-first-review-amendments.md)
delimita esta tarea documental y registra su verificación. Los hallazgos
anteriores se conservan como revisión de la base indicada, no como una lista
permanente de defectos del documento modificado.

Las enmiendas del diseño y CF-1 especifican adaptadores de review/revise que
conservan validación y datos de dominio, consumidores mantenidos concretos,
la ruta inicial de prompts no genéricos y retirada por declaración. El owner
de tipos recibe el contrato propuesto de uniones genéricas. Por decisión del
usuario, `S is-record` se conserva como límite explícito de la primera entrega:
es el valor transportado en el bucle y proyectado al agotar iteraciones. `I`
pierde esa restricción y permanece como entrada léxica fija. Esto resuelve el
hallazgo 8 mediante un límite documentado, no mediante generalización de `S`.

Corregir esos contratos no demuestra su implementación. La
[comprobación posterior de agotamiento](2026-09-28-cf1a-exhaustion-projection-check.md)
establece que la proyección de estado genérico record es expresable, pero queda
bloqueada por un arreglo acotado del selector del runtime: con `:max >= 2`
se pierde el último `continue`. El estado del prerrequisito es **holds, blocked
on a bounded runtime selector fix**, no abierto ni resuelto. La comprobación
local recoge dos tests: uno pasa y otro reproduce el defecto mediante `xfail`
estricto. Captura/reanudación y dependencia de `ctx` siguen sin demostrarse;
las nuevas capacidades conservan sus pruebas de aceptación. El fallo separado
de WCC con hooks puros inline como escrutinio de `match` exige usar hooks de
review respaldados por comandos o proveedores en las pruebas deterministas
de CF-1b; no añade un prerrequisito a CF-1.
La selección concurrente de CF-1a y la posición de CF-1b antes de R1b quedan
preservadas en la hoja de ruta, sin activar aquí CF-1b ni gasto de proveedores.
