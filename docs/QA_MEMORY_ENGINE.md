# Motor de Preguntas, Respuestas Híbrido y Banco de Memoria Persistente

Implementación diseñada por **Gemini NEON (Arquitecto)** y construida por **Gemini Argon (Constructor)** dentro de `backend/app/services/qa_engine/`.

## 1. Arquitectura
- **Modelos y Migración**: [`backend/app/memory_models.py`](../backend/app/memory_models.py) y migración [`0016_motor_qa_memoria_persistente.py`](../backend/migrations/versions/0016_motor_qa_memoria_persistente.py).
  - `fuentes_conocimiento` y `fragmentos_conocimiento`: almacenamiento estructural (sección, tipo de bloque `texto|tabla|lista`, tokens BM25 y vector semántico L2-normalizado).
  - `sesiones_memoria` y `mensajes_memoria`: memoria de **corto plazo** por sesión y usuario.
  - `memorias_episodicas`: memoria **episódica** a largo plazo con consolidación anti-olvido (`vigente`, `reemplaza_id`).
  - `memorias_entidad`: fichas consolidadas de entidades (`unidad`, `espacio`, `reglamento`, etc.).
  - `auditoria_consultas_ia`: registro de variantes expandidas, filtros de alcance, citas y bloqueos de seguridad.

## 2. Pipeline Q&A
1. **Guardrails (`guardrails.py`)**: bloqueo de *prompt injection*, prevención de acceso *cross-tenant* y redacción de secretos/tokens.
2. **Expansión semántica (`query_expansion.py`)**: normalización, stemming ligero en español, diccionario de sinónimos/jerga del dominio, tolerancia a typos contra vocabulario indexado y resolución de correferencias de sesión.
3. **Recuperación híbrida + Reranking (`hybrid_retriever.py`)**: BM25 + similitud coseno vectorial + fusión RRF + reranking por estructura, cobertura y sección.
4. **Cero alucinaciones (`orchestrator.py`)**: cita fuente y sección de cada fragmento; si no existe respaldo suficiente, responde `clasificacion: "sin_respaldo"` sin inventar cifras ni reglas.

## 3. Endpoints
- `POST /edificios/{edificio_id}/ia/indexar` (Admin): indexa reglamentos, documentos, comunicados, asambleas, espacios, incidencias y unidades.
- `POST /edificios/{edificio_id}/ia/preguntar`: responde preguntas naturales o no literales usando sesión y memoria persistente.
- `GET/POST /edificios/{edificio_id}/ia/memoria` y `DELETE /edificios/{edificio_id}/ia/memoria/{id}`: consulta, consolidación y desactivación trazable de memoria.
- `GET /edificios/{edificio_id}/ia/auditoria` (Admin): trazabilidad de consultas.
