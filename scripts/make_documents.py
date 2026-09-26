"""Generate DOCX deliverables (executive summary + technical report).

Reads the markdown sources from deliverables/ and renders structured DOCX
documents with the same content, then PDFs via ReportLab. Keeps everything
reproducible: run this script to rebuild the documents.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DELIV = ROOT / "deliverables"


def _add_runs(par, text: str):
    """Render **bold** and *italic* markdown spans inside a paragraph."""
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*|\*(.+?)\*", text):
        if m.start() > pos:
            par.add_run(text[pos:m.start()])
        if m.group(1) is not None:
            r = par.add_run(m.group(1))
            r.bold = True
        else:
            r = par.add_run(m.group(2))
            r.italic = True
        pos = m.end()
    if pos < len(text):
        par.add_run(text[pos:])


def md_to_docx(md_path: Path, docx_path: Path, title: str) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    lines = md_path.read_text(encoding="utf-8").splitlines()
    in_code = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            p = doc.add_paragraph()
            r = p.add_run(line)
            r.font.name = "Consolas"
            r.font.size = Pt(8.5)
            continue
        if not line.strip():
            continue
        if line.startswith("# "):
            h = doc.add_heading(line[2:].strip(), level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=1)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=2)
        elif line.strip() in ("---", "***"):
            continue
        elif line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, line[2:].strip())
        elif re.match(r"^\d+\. ", line):
            p = doc.add_paragraph(style="List Number")
            _add_runs(p, re.sub(r"^\d+\. ", "", line))
        elif line.startswith(">"):
            p = doc.add_paragraph()
            _add_runs(p, line.lstrip("> "))
            p.runs[0].italic = True if p.runs else None
        else:
            p = doc.add_paragraph()
            _add_runs(p, line.strip())
    doc.save(docx_path)
    print("wrote", docx_path)


if __name__ == "__main__":
    md_to_docx(
        DELIV / "executive_summary.md",
        DELIV / "executive_summary.docx",
        "GridShield AI — Executive Summary",
    )
