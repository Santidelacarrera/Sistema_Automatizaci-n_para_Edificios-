"""Regenera la matriz desde requisitos.json; no infiere estados ni resultados de pruebas."""
from collections import Counter, defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = json.loads((ROOT / "docs/requisitos.json").read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for r in rows:
        groups[r["modulo"]].append(r)
    lines = ["# Matriz de funcionalidades", "", "Revisión: 2026-11-16. Fuente: requisitos.json. No es una certificación de producción.", "",
        "El inventario transcribe las 459 viñetas funcionales de las secciones 3–24 del encargo. "
        "El porcentaje cuenta únicamente filas COMPLETADA Y PROBADA / filas del módulo; "
        "cada fila pesa lo mismo y las parciales valen cero. No mide líneas de código, esfuerzo, "
        "cobertura de tests ni porcentaje global de preparación comercial. "
        "Los requisitos en prosa y los 20 recorridos de aceptación se revisan por separado en FINAL_COMPLETION_REPORT.md. "
        "Repeticiones del encargo se conservan; no se usa el promedio como afirmación de cumplimiento total.", "",
        "Estados: COMPLETADA Y PROBADA; IMPLEMENTADA, PERO NO PROBADA; PARCIAL; SOLAMENTE INTERFAZ; "
        "NO IMPLEMENTADA; BLOQUEADA POR SERVICIO EXTERNO O HARDWARE.", "",
        "| Módulo | Completadas / criterios | Porcentaje estricto |", "|---|---:|---:|"]
    for title, rs in groups.items():
        n = sum(r["estado"] == "COMPLETADA Y PROBADA" for r in rs)
        lines.append(f"| {title} | {n}/{len(rs)} | {100*n/len(rs):.1f}% |")
    counts = Counter(r["estado"] for r in rows)
    lines += ["", "Distribución: " + "; ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + ".", ""]
    for title, rs in groups.items():
        lines += [f"## {title}", "", "| ID | Requisito | Estado | Evidencia y alcance | Pendiente |", "|---|---|---|---|---|"]
        for r in rs:
            values = [r[k].replace("|", "/").replace("\n", " ") for k in ("id", "requisito", "estado", "evidencia", "pendiente")]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    (ROOT / "docs/FEATURE_COMPLETION_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} criterios; {counts['COMPLETADA Y PROBADA']} completados y probados.")


if __name__ == "__main__":
    main()
