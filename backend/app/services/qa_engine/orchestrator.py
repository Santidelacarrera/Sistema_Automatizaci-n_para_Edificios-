"""Orquestador del Motor Q&A Híbrido y Banco de Memoria Persistente."""
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import utcnow
from ...memory_models import (
    AuditoriaConsultaIA,
    FragmentoConocimiento,
    FuenteConocimiento,
)
from ...models import Comunicado, Edificio, EspacioComun, Unidad
from ...operations_models import Asamblea, Documento, Incidencia, ReglamentoInterno
from ...security import Principal
from .. import llm
from .chunking import chunkear_documento
from .guardrails import detectar_prompt_injection, redactar_secretos, sanitizar_entrada_externa
from .hybrid_retriever import calcular_embedding, recuperar_y_rerankear
from .memory_bank import (
    buscar_memorias_entidad,
    buscar_memorias_episodicas,
    guardar_memoria_episodica,
    obtener_historial_sesion,
    obtener_o_crear_sesion,
    registrar_turno_sesion,
    upsert_memoria_entidad,
)
from .query_expansion import expandir_consulta, tokenizar


def _indexar_fuente(
    db: Session,
    edificio_id: str,
    tipo_fuente: str,
    referencia_id: int,
    titulo: str,
    texto: str,
    publico_comunidad: bool = True,
    unidad_id: int | None = None,
) -> int:
    limpio = sanitizar_entrada_externa(texto)
    if not limpio.strip():
        return 0
    h = hashlib.sha256(f"{titulo}|{publico_comunidad}|{unidad_id}|{limpio}".encode("utf-8")).hexdigest()
    fuente = db.scalar(select(FuenteConocimiento).where(
        FuenteConocimiento.edificio_id == edificio_id,
        FuenteConocimiento.tipo_fuente == tipo_fuente,
        FuenteConocimiento.referencia_id == referencia_id,
    ))
    if fuente and fuente.hash_contenido == h:
        return 0
    if fuente:
        db.query(FragmentoConocimiento).filter(FragmentoConocimiento.fuente_id == fuente.id).delete()
        fuente.titulo = titulo[:200]
        fuente.publico_comunidad = publico_comunidad
        fuente.unidad_id = unidad_id
        fuente.hash_contenido = h
        fuente.actualizado = utcnow()
    else:
        fuente = FuenteConocimiento(
            edificio_id=edificio_id,
            tipo_fuente=tipo_fuente,
            referencia_id=referencia_id,
            titulo=titulo[:200],
            publico_comunidad=publico_comunidad,
            unidad_id=unidad_id,
            hash_contenido=h,
        )
        db.add(fuente)
        db.flush()

    chunks = chunkear_documento(limpio, titulo=titulo)
    for ch in chunks:
        toks = tokenizar(ch.contenido)
        emb = calcular_embedding(ch.contenido, tokens_extra=toks)
        db.add(FragmentoConocimiento(
            fuente_id=fuente.id,
            edificio_id=edificio_id,
            unidad_id=unidad_id,
            publico_comunidad=publico_comunidad,
            orden=ch.orden,
            seccion=ch.seccion[:200],
            tipo_bloque=ch.tipo_bloque,
            contenido=ch.contenido,
            tokens_bm25=toks,
            embedding_json=emb,
            metadatos_json={**ch.metadatos, "tipo_fuente": tipo_fuente, "referencia_id": referencia_id},
        ))
    db.flush()
    return len(chunks)


def indexar_edificio(db: Session, edificio_id: str) -> dict:
    """Indexa fuentes estructuradas del edificio y consolida memorias de entidad."""
    ed = db.get(Edificio, edificio_id)
    if not ed:
        return {"fuentes": 0, "fragmentos": 0}
    fragmentos_nuevos = 0

    for reg in db.scalars(select(ReglamentoInterno).where(ReglamentoInterno.edificio_id == edificio_id, ReglamentoInterno.vigente.is_(True))).all():
        n = _indexar_fuente(db, edificio_id, "reglamento", reg.id, f"{reg.titulo} v{reg.version}", reg.contenido, publico_comunidad=True)
        fragmentos_nuevos += n
        upsert_memoria_entidad(
            db, edificio_id, "reglamento", f"reg:{reg.id}",
            {"titulo": reg.titulo, "version": reg.version, "vigente": reg.vigente},
            [f"Reglamento '{reg.titulo}' versión {reg.version} vigente."],
            fuente_ref=f"reglamento:{reg.id}",
        )

    for com in db.scalars(select(Comunicado).where(Comunicado.edificio_id == edificio_id).order_by(Comunicado.id.desc()).limit(100)).all():
        fragmentos_nuevos += _indexar_fuente(db, edificio_id, "comunicado", com.id, com.titulo, com.cuerpo, publico_comunidad=True)

    for doc in db.scalars(select(Documento).where(Documento.edificio_id == edificio_id).order_by(Documento.id.desc()).limit(150)).all():
        cuerpo_doc = f"Documento categoría {doc.categoria}. Vence: {doc.vence or 'sin vencimiento'}."
        fragmentos_nuevos += _indexar_fuente(
            db, edificio_id, "documento", doc.id, doc.titulo, cuerpo_doc, publico_comunidad=bool(doc.publico_comunidad),
        )

    for asamb in db.scalars(select(Asamblea).where(Asamblea.edificio_id == edificio_id).order_by(Asamblea.id.desc()).limit(50)).all():
        texto_asamb = f"# Agenda\n{asamb.agenda}\n\n# Acta\n{asamb.acta or 'Pendiente de cierre'}"
        fragmentos_nuevos += _indexar_fuente(
            db, edificio_id, "asamblea", asamb.id, f"Asamblea: {asamb.titulo}", texto_asamb, publico_comunidad=True,
        )

    for esp in db.scalars(select(EspacioComun).where(EspacioComun.edificio_id == edificio_id)).all():
        texto_esp = (
            f"Espacio común {esp.nombre}. Tarifa: CLP {float(esp.tarifa):,.0f}. "
            f"Garantía: CLP {float(esp.garantia):,.0f}. Aforo máximo: {esp.aforo} personas."
        )
        fragmentos_nuevos += _indexar_fuente(db, edificio_id, "espacio", esp.id, f"Espacio: {esp.nombre}", texto_esp, publico_comunidad=True)
        upsert_memoria_entidad(
            db, edificio_id, "espacio", esp.nombre.lower(),
            {"tarifa": float(esp.tarifa), "garantia": float(esp.garantia), "aforo": esp.aforo},
            [texto_esp],
            fuente_ref=f"espacio:{esp.id}",
        )

    for inc in db.scalars(select(Incidencia).where(Incidencia.edificio_id == edificio_id).order_by(Incidencia.id.desc()).limit(100)).all():
        texto_inc = f"Incidencia #{inc.id} ({inc.estado}, prioridad {inc.prioridad}): {inc.titulo}. {inc.descripcion}"
        fragmentos_nuevos += _indexar_fuente(
            db, edificio_id, "incidencia", inc.id, inc.titulo, texto_inc,
            publico_comunidad=(inc.unidad_id is None), unidad_id=inc.unidad_id,
        )

    for u in db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)).all():
        upsert_memoria_entidad(
            db, edificio_id, "unidad", u.numero,
            {"numero": u.numero, "torre": u.torre or "", "piso": u.piso, "coeficiente": float(u.coeficiente)},
            [f"Departamento {u.numero} (torre '{u.torre or 'principal'}', piso {u.piso or '-'}), coeficiente {float(u.coeficiente):.4f}."],
            fuente_ref=f"unidad:{u.id}", unidad_id=u.id,
        )

    total_fuentes = db.query(FuenteConocimiento).filter(FuenteConocimiento.edificio_id == edificio_id).count()
    total_frag = db.query(FragmentoConocimiento).filter(FragmentoConocimiento.edificio_id == edificio_id).count()
    return {"fuentes": total_fuentes, "fragmentos_totales": total_frag, "fragmentos_nuevos": fragmentos_nuevos}


def responder_pregunta(
    db: Session,
    edificio_id: str,
    user: Principal,
    pregunta: str,
    unidad_id_restringida: int | None = None,
    sesion_uuid: str | None = None,
    guardar_memoria: bool = True,
) -> dict:
    """Pipeline completo: Guardrails -> Sesión -> Expansión -> Híbrido+Rerank -> Memoria -> Zero-Hallucination."""
    bloqueado, motivo_bloq = detectar_prompt_injection(pregunta, edificio_id)
    filtros = {"edificio_id": edificio_id, "rol": user.rol.value, "unidad_id_restringida": unidad_id_restringida}
    if bloqueado:
        db.add(AuditoriaConsultaIA(
            edificio_id=edificio_id, residente_id=user.residente_id, rol=user.rol.value,
            pregunta_sanitizada=redactar_secretos(pregunta)[:500], variantes_consulta=[],
            filtros_alcance=filtros, fuentes_citadas=[], bloqueo_seguridad=True, modo_respuesta="bloqueado_seguridad",
        ))
        db.commit()
        return {
            "respuesta": motivo_bloq,
            "clasificacion": "bloqueado_seguridad",
            "sesion_uuid": sesion_uuid,
            "fuentes": [],
            "memorias_usadas": [],
            "variantes_consulta": [],
            "bloqueo_seguridad": True,
        }

    sesion = obtener_o_crear_sesion(db, edificio_id, user.residente_id, unidad_id_restringida, sesion_uuid)
    hist_sesion = obtener_historial_sesion(db, sesion.id)

    # Pre-filtro estricto por edificio y alcance de usuario
    q_frag = select(FragmentoConocimiento).where(FragmentoConocimiento.edificio_id == edificio_id)
    if unidad_id_restringida is not None:
        q_frag = q_frag.where(
            (FragmentoConocimiento.publico_comunidad.is_(True)) | (FragmentoConocimiento.unidad_id == unidad_id_restringida)
        )
    fragmentos = db.scalars(q_frag).all()

    vocab = set()
    for f in fragmentos:
        vocab.update(f.tokens_bm25 or [])

    exp = expandir_consulta(
        pregunta, vocabulario_indexado=vocab,
        historial_sesion=hist_sesion, entidades_activas=list(sesion.entidades_activas or []),
    )
    vec_q = calcular_embedding(exp["pregunta_resuelta"], tokens_extra=exp["tokens_expandidos"])
    hits = recuperar_y_rerankear(fragmentos, exp["tokens_base"], exp["tokens_expandidos"], vec_q, top_k=5)

    mems_ep = buscar_memorias_episodicas(db, edificio_id, exp["tokens_expandidos"], unidad_id_restringida, limite=4)
    mems_ent = buscar_memorias_entidad(db, edificio_id, exp["tokens_expandidos"], unidad_id_restringida, limite=4)

    # Analítica operativa solo cuando la consulta toca finanzas/morosidad/incidencias o pide análisis
    toks_set = set(exp["tokens_expandidos"])
    es_financiera_u_operativa = bool(toks_set & {"morosidad", "deuda", "saldo", "caja", "incidencia", "presupuesto", "circular"})
    analisis_datos = None
    if es_financiera_u_operativa:
        analisis_datos = llm.responder_consulta(db, edificio_id, exp["pregunta_resuelta"], unidad_id_restringida)

    fuentes_out = [
        {
            "fragmento_id": h["fragmento"].id,
            "seccion": h["fragmento"].seccion,
            "tipo_bloque": h["fragmento"].tipo_bloque,
            "score": h["score_final"],
            "extracto": redactar_secretos(h["fragmento"].contenido[:280]),
            "metadatos": h["fragmento"].metadatos_json,
        }
        for h in hits
    ]
    memorias_out = (
        [{"tipo": "episodica", "id": m.id, "tema": m.clave_tema, "resumen": redactar_secretos(m.resumen)} for m in mems_ep]
        + [{"tipo": "entidad", "id": e.id, "clave": f"{e.entidad_tipo}:{e.entidad_clave}", "hechos": e.hechos_verificados[:3]} for e in mems_ent]
    )

    # Construcción de respuesta con regla estricta Zero-Hallucination
    partes = []
    clasificacion = "sin_respaldo"
    if hits:
        clasificacion = "evidencia_indexada"
        partes.append("Basado en la documentación y registros verificados del edificio:")
        for f in fuentes_out[:3]:
            titulo = (f["metadatos"] or {}).get("titulo") or f["seccion"]
            partes.append(f"- [Fuente: {titulo} · Sección: {f['seccion']}] {f['extracto']}")
    if mems_ep or mems_ent:
        if clasificacion == "sin_respaldo":
            clasificacion = "memoria_persistente"
        partes.append("Memoria persistente relacionada:")
        for m in mems_ep[:2]:
            partes.append(f"- [Memoria episódica #{m.id} ({m.clave_tema})] {redactar_secretos(m.resumen)}")
        for e in mems_ent[:2]:
            if e.hechos_verificados:
                partes.append(f"- [Entidad {e.entidad_tipo}:{e.entidad_clave}] {redactar_secretos(e.hechos_verificados[0])}")
    if analisis_datos and analisis_datos.get("respuesta"):
        if clasificacion == "sin_respaldo":
            clasificacion = "evidencia_indexada"
        partes.append(f"Datos operativos vigentes: {redactar_secretos(analisis_datos['respuesta'])}")

    if not partes:
        respuesta_final = (
            "No encontré evidencia verificada en la base documental ni en la memoria del edificio "
            "para responder con certeza a esta consulta. No inventaré cifras ni reglas: "
            "indexe el reglamento/documento correspondiente o reformule con más detalle."
        )
        clasificacion = "sin_respaldo"
    else:
        respuesta_final = "\n".join(partes)

    entidades_detectadas = [f"{e.entidad_tipo}:{e.entidad_clave}" for e in reversed(mems_ent[:2])]
    registrar_turno_sesion(db, sesion, "usuario", redactar_secretos(pregunta), entidades_detectadas)
    registrar_turno_sesion(db, sesion, "asistente", respuesta_final[:1000], entidades_detectadas)

    if guardar_memoria and clasificacion != "sin_respaldo":
        tema = "_".join(exp["tokens_base"][:4]) or "consulta_general"
        guardar_memoria_episodica(
            db, edificio_id, categoria="consulta", clave_tema=tema,
            resumen=f"Consulta '{redactar_secretos(pregunta)[:100]}' -> {respuesta_final[:240]}",
            hechos_clave=[f["seccion"] for f in fuentes_out[:3]],
            fuente_ref=f"sesion:{sesion.sesion_uuid}",
            residente_id=user.residente_id, unidad_id=unidad_id_restringida,
        )

    db.add(AuditoriaConsultaIA(
        edificio_id=edificio_id, residente_id=user.residente_id, rol=user.rol.value,
        pregunta_sanitizada=redactar_secretos(pregunta)[:500],
        variantes_consulta=exp["variantes"],
        filtros_alcance=filtros,
        fuentes_citadas=[{"seccion": f["seccion"], "score": f["score"]} for f in fuentes_out],
        bloqueo_seguridad=False,
        modo_respuesta=clasificacion,
    ))
    db.commit()

    return {
        "respuesta": respuesta_final,
        "clasificacion": clasificacion,
        "sesion_uuid": sesion.sesion_uuid,
        "pregunta_resuelta": exp["pregunta_resuelta"],
        "variantes_consulta": exp["variantes"],
        "fuentes": fuentes_out,
        "memorias_usadas": memorias_out,
        "borrador_circular": analisis_datos.get("borrador_circular") if analisis_datos else None,
        "bloqueo_seguridad": False,
    }
