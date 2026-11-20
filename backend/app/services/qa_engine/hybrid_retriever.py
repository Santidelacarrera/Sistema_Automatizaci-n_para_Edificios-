"""Recuperación híbrida (BM25 + Vectorial semántico) con Fusión RRF y Reranking profundo."""
import hashlib
import math

from .query_expansion import normalizar_texto, tokenizar

EMBED_DIM = 128


def calcular_embedding(texto: str, tokens_extra: list[str] | None = None) -> list[float]:
    """Embedding denso determinista L2-normalizado (tokens + n-gramas de caracteres)."""
    vec = [0.0] * EMBED_DIM
    toks = tokens_extra if tokens_extra is not None else tokenizar(texto)
    norm_txt = normalizar_texto(texto)

    # Señal léxica + stems
    for t in toks:
        h = int(hashlib.blake2b(t.encode("utf-8"), digest_size=8).hexdigest(), 16)
        idx = h % EMBED_DIM
        signo = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        vec[idx] += signo * 1.5

    # Señal sub-palabra (trigramas) para capturar similitud morfológica y typos
    compacto = f" {norm_txt} "
    for i in range(max(0, len(compacto) - 2)):
        tri = compacto[i:i + 3]
        h = int(hashlib.blake2b(tri.encode("utf-8"), digest_size=8).hexdigest(), 16)
        idx = h % EMBED_DIM
        signo = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        vec[idx] += signo * 0.35

    norma = math.sqrt(sum(v * v for v in vec))
    if norma <= 1e-9:
        return vec
    return [round(v / norma, 6) for v in vec]


def similitud_coseno(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


def score_bm25(query_tokens: list[str], doc_tokens: list[str], avg_dl: float, df_map: dict[str, int], total_docs: int) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    k1 = 1.5
    b = 0.75
    dl = len(doc_tokens)
    tf_map: dict[str, int] = {}
    for dt in doc_tokens:
        tf_map[dt] = tf_map.get(dt, 0) + 1
    score = 0.0
    for qt in set(query_tokens):
        tf = tf_map.get(qt, 0)
        if tf == 0:
            continue
        df = df_map.get(qt, 0)
        idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1.0 - b + b * (dl / max(1.0, avg_dl)))
        score += idf * ((tf * (k1 + 1.0)) / denom)
    return score


def recuperar_y_rerankear(
    fragmentos: list,
    tokens_base: list[str],
    tokens_expandidos: list[str],
    vec_consulta: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Ejecuta búsqueda híbrida (BM25 + vectorial) + RRF + reranker profundo."""
    if not fragmentos:
        return []

    total_docs = len(fragmentos)
    avg_dl = sum(max(1, len(f.tokens_bm25 or [])) for f in fragmentos) / total_docs
    df_map: dict[str, int] = {}
    for f in fragmentos:
        for t in set(f.tokens_bm25 or []):
            df_map[t] = df_map.get(t, 0) + 1

    candidatos = []
    for f in fragmentos:
        doc_toks = f.tokens_bm25 or []
        bm25_exacto = score_bm25(tokens_base, doc_toks, avg_dl, df_map, total_docs)
        bm25_exp = score_bm25(tokens_expandidos, doc_toks, avg_dl, df_map, total_docs)
        cos = similitud_coseno(vec_consulta, f.embedding_json or [])
        sec_toks = set(tokenizar(f.seccion or ""))
        cobertura_sec = len(set(tokens_expandidos) & sec_toks) / max(1, len(set(tokens_base)))
        cobertura_doc = len(set(tokens_expandidos) & set(doc_toks)) / max(1, len(set(tokens_base)))

        candidatos.append({
            "fragmento": f,
            "bm25": bm25_exacto * 1.2 + bm25_exp * 0.8,
            "vectorial": max(0.0, cos),
            "cobertura": min(1.0, cobertura_doc * 0.7 + cobertura_sec * 0.5),
        })

    # Ranking por cada rama para Reciprocal Rank Fusion (RRF)
    por_bm25 = sorted(candidatos, key=lambda x: -x["bm25"])
    por_vec = sorted(candidatos, key=lambda x: -x["vectorial"])
    rank_bm25 = {id(c["fragmento"]): i + 1 for i, c in enumerate(por_bm25)}
    rank_vec = {id(c["fragmento"]): i + 1 for i, c in enumerate(por_vec)}

    k_rrf = 30.0
    for c in candidatos:
        fid = id(c["fragmento"])
        rrf = (1.0 / (k_rrf + rank_bm25[fid])) + (1.0 / (k_rrf + rank_vec[fid]))
        # Reranking profundo: combina RRF, fuerza vectorial, cobertura conceptual y boost de sección/tabla
        boost_estructura = 0.08 if (c["fragmento"].tipo_bloque in ("tabla", "lista")) else 0.0
        c["score_final"] = round(
            rrf * 10.0 + c["vectorial"] * 0.65 + c["cobertura"] * 0.45 + (0.25 if c["bm25"] > 0 else 0.0) + boost_estructura,
            4,
        )

    ordenados = sorted(candidatos, key=lambda x: -x["score_final"])
    # Filtra fragmentos con señal real (evita devolver ruido irrelevante para habilitar Zero-Hallucination)
    relevantes = [c for c in ordenados if c["bm25"] > 0 or c["vectorial"] >= 0.22 or c["cobertura"] >= 0.34]
    return relevantes[:top_k]
