"""Documentos de consulta contable; no son documentos tributarios electrónicos."""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def pdf(titulo, subtitulo, cabecera, filas, notas=()):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    def p(texto):
        return Paragraph(escape(str(texto)), styles["BodyText"])
    content = [Paragraph(escape(titulo), styles["Title"]), p(subtitulo), Spacer(1, 18)]
    tabla = Table([[p(c) for c in cabecera]] + [[p(c) for c in fila] for fila in filas], repeatRows=1, hAlign="LEFT")
    tabla.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7efe9")),
                              ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#a8b8ac")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    content.append(tabla)
    for nota in notas:
        content.extend([Spacer(1, 12), p(nota)])
    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, title=titulo).build(content)
    return buffer.getvalue()
