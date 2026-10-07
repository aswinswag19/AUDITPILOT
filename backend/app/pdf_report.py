"""
Phase 6: PDF report generation using ReportLab.
Generates verified, refusal, and blocked audit reports in PDF format.
"""

from pathlib import Path
from xml.sax.saxutils import escape
from typing import Literal, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_audit_pdf(
    proof_bundle: Dict[str, Any],
    output_path: Path,
    report_type: Literal["verified", "refusal", "blocked"]
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=15
    )
    
    body_style = ParagraphStyle(
        'ReportBody',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#334155"),
        spaceAfter=8
    )

    story = []

    def e(value) -> str:
        return escape(str(value))

    def bullets(title: str, items) -> None:
        if items:
            story.append(Paragraph(f"<b>{e(title)}</b>", body_style))
            for item in items:
                story.append(Paragraph(f"&bull; {e(item)}", body_style))

    if report_type == "verified":
        story.append(Paragraph("AuditPilot Verified Proof Report", title_style))
        story.append(Paragraph(f"<b>Proof ID:</b> {e(proof_bundle.get('proof_id', 'N/A'))}", body_style))
        story.append(Paragraph(f"<b>Business Answer:</b> {e(proof_bundle.get('answer', 'N/A'))} {e(proof_bundle.get('currency', 'INR'))}", body_style))
        conv = proof_bundle.get("conversion") or {}
        if conv:
            basis_label = {"transaction_date": "rate on each transaction's date",
                           "latest": "present (latest) rate on file"}.get(conv.get("basis"), conv.get("basis"))
            story.append(Paragraph(f"<b>Currency conversion basis:</b> {e(basis_label)}", body_style))
            cmap = conv.get("currency_map") or {}
            reassigned = {k: v for k, v in cmap.items() if k != v}
            confirmed = [k for k, v in cmap.items() if k == v]
            if confirmed:
                story.append(Paragraph(f"<b>Currencies confirmed by the user:</b> {e(', '.join(confirmed))}", body_style))
            if reassigned:
                story.append(Paragraph("<b>Currencies reassigned by the user:</b> "
                                       + e(", ".join(f"{k} -> {v}" for k, v in reassigned.items())), body_style))
        story.append(Paragraph(f"<b>Trust Status:</b> {e(proof_bundle.get('trust_decision', 'N/A'))} (Analyst and Inspector results match)", body_style))
        story.append(Paragraph(f"<b>Publishability:</b> {e(proof_bundle.get('publishability', 'MANAGEMENT_REVIEW_REQUIRED'))}", body_style))
        if proof_bundle.get("script_reproduced_result"):
            story.append(Paragraph(f"<b>Independent proof script reproduced:</b> {e(proof_bundle['script_reproduced_result'])}", body_style))
        bullets("Reasons", proof_bundle.get("reasons"))
        bullets("Remaining risks", proof_bundle.get("remaining_risks"))

        impact = proof_bundle.get("impact") or {}
        if impact.get("raw_total_before_cleaning") is not None:
            story.append(Paragraph("<b>Impact of data cleaning</b>", body_style))
            rows = [
                ["Raw total before cleaning", impact.get("raw_total_before_cleaning")],
                ["Exact duplicate rows", impact.get("duplicate_effect")],
                ["Conflicting invoices", impact.get("conflict_effect")],
                ["Refunds", impact.get("refund_effect")],
                ["Verified total", impact.get("verified_total")],
            ]
            table = Table([[Paragraph(e(k), body_style), Paragraph(e(v), body_style)] for k, v in rows], colWidths=[250, 250])
            table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1"))]))
            story.append(table)
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"<b>Unsupported currency:</b> {e(impact.get('unsupported_currency_effect'))}", body_style))
            story.append(Paragraph(f"<b>Largest monetary risk:</b> {e(impact.get('largest_monetary_risk'))}", body_style))
            story.append(Paragraph(f"<b>Recommended cleanup:</b> {e(impact.get('minimum_cleanup_recommendation'))}", body_style))

        sens = proof_bundle.get("sensitivity") or {}
        if sens.get("materiality"):
            story.append(Paragraph(f"<b>Sensitivity to interpretation:</b> {e(sens['materiality'])}. {e(sens.get('explanation', ''))}", body_style))

        story.append(Spacer(1, 10))
        story.append(Paragraph("Disclaimer: This report supports data analysis and review. It does not replace independent financial or audit review.", body_style))
    elif report_type == "refusal":
        story.append(Paragraph("AuditPilot Analysis Refusal Report", title_style))
        story.append(Paragraph("No financial result was published because available data could not support a reliable answer.", body_style))
        if proof_bundle.get("reason"):
            story.append(Paragraph(f"<b>Reason:</b> {e(proof_bundle['reason'])}", body_style))
    else:
        story.append(Paragraph("AuditPilot Analysis Blocked Report", title_style))
        story.append(Paragraph("No financial result was published due to data risks or engine verification mismatch.", body_style))
        if proof_bundle.get("reason"):
            story.append(Paragraph(f"<b>Reason:</b> {e(proof_bundle['reason'])}", body_style))
        bullets("Reasons", proof_bundle.get("reasons"))

    doc.build(story)
    return output_path

