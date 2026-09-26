"""Build the GridShield AI pitch deck (PPTX, 10 slides, dark theme).

Content mirrors deliverables/pitch_deck.md; run to regenerate.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables" / "pitch_deck.pptx"

BG = RGBColor(0x0B, 0x12, 0x20)
FG = RGBColor(0xE2, 0xE8, 0xF0)
MUT = RGBColor(0x94, 0xA3, 0xB8)
ACC = RGBColor(0x38, 0xBD, 0xF8)
GRN = RGBColor(0x22, 0xC5, 0x5E)
RED = RGBColor(0xEF, 0x44, 0x44)
AMB = RGBColor(0xF5, 0x9E, 0x0B)

SLIDES = [
    ("Problem", "The grid's sensors can lie — and operators act on it.", [
        ("Millions of smart meters, inverters and SCADA nodes = millions of entry points", MUT),
        ("A false-data injection skews what operators see; a hijacked command skews what they do", MUT),
        ("Energy tools trust all data; security tools don't understand energy", MUT),
        ("Wrong dispatch, avoidable imports, blackouts — discovered too late", RED),
    ]),
    ("Solution", "GridShield AI: predict, protect, optimize — through attacks.", [
        ("Live digital twin of a solar + battery campus microgrid", FG),
        ("AI detects when data lies, explains why, isolates the traitor device", FG),
        ("Keeps operating on reconstructed trusted values", GRN),
        ("Re-optimizes the battery in seconds — resilience, not just alerts", GRN),
    ]),
    ("How it works", "Twin → AI → response, in one 1-second loop.", [
        ("Twin: deterministic physics, 5-min steps — solar, battery, grid, 6 buildings, SCADA", FG),
        ("AI: forecasters → 5-channel hybrid detector → classifier → explanations", FG),
        ("Response: isolate → reconstruct → MPC re-solve → audit log → re-admit", GRN),
        ("FastAPI + WebSocket backend, React dashboard — runs on a laptop", ACC),
    ]),
    ("Digital twin", "Two data planes — the core trick.", [
        ("RAW plane = exactly what SCADA sees (attacked)", AMB),
        ("TRUSTED plane = what the AI forecasts and controls with", GRN),
        ("Attacks corrupt the view, never the physics — like real FDI", FG),
        ("Twin + attacks + detection in one loop = measurable resilience", FG),
    ]),
    ("AI", "Lightweight models, calibrated decisions.", [
        ("Forecast: solar 10.3 kW / demand 7.1 kW MAE — trained in <1 s", FG),
        ("Detect: 5 evidence channels incl. control-plane consistency — the battery must obey the defender's plan", FG),
        ("Threshold calibrated at P99.5 of clean traffic → 0.5% false positives by construction", GRN),
        ("Measured: precision 1.00 · first alert in 1 step · 5/5 attack classes", GRN),
    ]),
    ("Cyber defense — live demo", "One click, full chain.", [
        ("FDI_BULK launches; metered load jumps +35% — physics untouched", AMB),
        ("ATTACK → DETECTION → EXPLANATION → DEFENSE → RECONSTRUCTION → RE-OPTIMIZATION → RECOVERY", FG),
        ("Jury-readable explanations: reasons, evidence, threshold, attributions", FG),
        ("Same seed ⇒ identical run, every time", ACC),
    ]),
    ("Results", "Measured, reproducible — never invented.", [
        ("Detection: precision 1.00 · FPR 0.5% · latency 1 step (all 5 attack classes)", GRN),
        ("Response: hijack exposure 25 → 5 min; battery deviation −80%", GRN),
        ("Federated FedAvg: global MAE 7.06 kW = centralized baseline, zero raw data shared", FG),
        ("34 tests green; every number from scripts/run_experiments.py", ACC),
    ]),
    ("Impact & scalability", "From campus to feeder.", [
        ("Users: campuses, distribution operators, industrial parks", FG),
        ("Value: corrupted-decision minutes avoided; battery assets protected; audit trail", FG),
        ("Deploy: same data contract against a real historian; per-feeder detectors; ms per tick", ACC),
        ("Societal: automation that explains itself in critical infrastructure", GRN),
    ]),
    ("Innovation & bonus areas", "All five target areas addressed.", [
        ("Digital twin with two data planes  ✓", GRN),
        ("Explainable AI on every alert  ✓", GRN),
        ("Live cyberattack demonstration (local, safe)  ✓", GRN),
        ("Federated learning FedAvg PoC — weights only  ✓", GRN),
        ("Control-plane detection channel — catches what telemetry-only detectors miss", AMB),
    ]),
    ("Conclusion & roadmap", "Predict. Protect. Optimize.", [
        ("Next: real SCADA ingestion (IEC 61850) · probabilistic forecasts · SHAP in production · federated detection · hardware-in-the-loop", FG),
        ("The detect → explain → contain → reconstruct → optimize loop is ready today", GRN),
        ("GridShield AI — trustworthy energy automation under attack", ACC),
    ]),
]


def build() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    for i, (title, subtitle, bullets) in enumerate(SLIDES, start=1):
        s = prs.slides.add_slide(blank)
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = BG

        # kicker
        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.45), Inches(12), Inches(0.4))
        p = tb.text_frame.paragraphs[0]
        r = p.add_run(); r.text = f"GRIDSHIELD AI   ·   {i:02d}/10"
        r.font.size = Pt(12); r.font.color.rgb = MUT; r.font.bold = True

        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.95), Inches(12.1), Inches(1.1))
        p = tb.text_frame.paragraphs[0]
        r = p.add_run(); r.text = title
        r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = FG

        tb = s.shapes.add_textbox(Inches(0.6), Inches(1.95), Inches(12.1), Inches(0.7))
        p = tb.text_frame.paragraphs[0]
        r = p.add_run(); r.text = subtitle
        r.font.size = Pt(20); r.font.color.rgb = ACC

        tb = s.shapes.add_textbox(Inches(0.75), Inches(2.9), Inches(11.8), Inches(4.2))
        tf = tb.text_frame
        tf.word_wrap = True
        for j, (text, color) in enumerate(bullets):
            p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
            p.space_after = Pt(14)
            r = p.add_run(); r.text = "▸  " + text
            r.font.size = Pt(17); r.font.color.rgb = color

        if i == 10:
            tb = s.shapes.add_textbox(Inches(0.6), Inches(6.7), Inches(12), Inches(0.5))
            p = tb.text_frame.paragraphs[0]
            r = p.add_run(); r.text = "IEEE SmartSecureGrid Challenge 2026 — Proof of Concept (video excluded from repo; recorded separately)"
            r.font.size = Pt(11); r.font.color.rgb = MUT

    prs.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
