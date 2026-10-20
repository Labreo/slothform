"""Synthetic document generator producing compliant PDF resumes and tax documents for form uploads."""

import os
import uuid
from typing import Any, Dict, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class SyntheticDocumentGenerator:
    """Generates standard PDF resumes and tax forms on the fly when static files are missing."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.getcwd(), "artifacts", "documents")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_resume(
        self,
        profile: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Generates a compliant 1-page PDF software engineer resume.
        Returns the absolute filesystem path of the generated PDF.
        """
        data = profile or {}
        candidate_name = data.get("full_name") or data.get("name") or "Aarav Sharma"
        email = data.get("email") or "aarav.sharma@example.com"
        phone = data.get("phone") or "+91 98765 43210"
        location = data.get("location") or "Bengaluru, Karnataka, India"
        linkedin = data.get("linkedin") or "https://linkedin.com/in/aaravsharma-dev"
        github = data.get("github") or "https://github.com/aaravsharma"

        if not filename:
            unique_suffix = uuid.uuid4().hex[:8]
            clean_name = candidate_name.lower().replace(" ", "_")
            filename = f"resume_{clean_name}_{unique_suffix}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ResumeTitle",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "ResumeSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "ResumeSectionHeading",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0f172a"),
            borderPadding=2,
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "ResumeBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155"),
        )

        story = []

        # Header
        story.append(Paragraph(candidate_name, title_style))
        contact_line = f"{email} | {phone} | {location}<br/>LinkedIn: {linkedin} | GitHub: {github}"
        story.append(Paragraph(contact_line, subtitle_style))
        story.append(Spacer(1, 4))

        # Summary
        story.append(Paragraph("PROFESSIONAL SUMMARY", heading_style))
        summary_text = data.get(
            "summary",
            "Senior Full-Stack & Systems Engineer with 6+ years of experience architecting distributed "
            "backends, autonomous agents, and cloud automation platforms. Proven track record in high-throughput "
            "Python/FastAPI services, Playwright browser automation, and privacy-preserving identity systems."
        )
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 4))

        # Experience
        story.append(Paragraph("WORK EXPERIENCE", heading_style))
        experiences = data.get("experience", [
            {
                "title": "Lead Software Engineer",
                "company": "Apex Distributed Labs",
                "period": "2023 - Present",
                "points": [
                    "Architected cloud automation pipelines handling 50,000+ daily headless browser tasks via Playwright and CDP.",
                    "Implemented zero-trust identity vault and OIDC backchannel authorization for agentic workflows.",
                    "Cut task execution latency by 42% through connection pooling and intelligent DOM extraction."
                ],
            },
            {
                "title": "Full-Stack Software Engineer",
                "company": "Vanguard Cloud Technologies",
                "period": "2020 - 2023",
                "points": [
                    "Engineered asynchronous FastAPI microservices serving over 2M requests daily with sub-50ms p95 latency.",
                    "Built dynamic form ingestion workflows for cross-origin iframes and complex interactive web interfaces."
                ],
            },
        ])

        for exp in experiences:
            exp_header = f"<b>{exp['title']}</b> — {exp['company']} <i>({exp['period']})</i>"
            story.append(Paragraph(exp_header, body_style))
            for pt in exp.get("points", []):
                bullet = f"• {pt}"
                story.append(Paragraph(bullet, body_style))
            story.append(Spacer(1, 4))

        # Skills
        story.append(Paragraph("TECHNICAL SKILLS", heading_style))
        skills_text = (
            "<b>Languages:</b> Python, TypeScript, SQL, Go<br/>"
            "<b>Frameworks & Tools:</b> FastAPI, Playwright, Browserbase, Pydantic, Docker, Redis, ReportLab<br/>"
            "<b>Cloud & Security:</b> AWS, Render, Auth0, OIDC CIBA, AES-256-GCM, Residential Proxies"
        )
        story.append(Paragraph(skills_text, body_style))
        story.append(Spacer(1, 4))

        # Education
        story.append(Paragraph("EDUCATION", heading_style))
        edu_text = "<b>B.Tech in Computer Science & Engineering</b> — National Institute of Technology (NIT), 2020"
        story.append(Paragraph(edu_text, body_style))

        doc.build(story)
        return os.path.abspath(filepath)

    def generate_tax_document(
        self,
        profile: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Generates a compliant IRS Form W-8BEN Certificate of Foreign Status fallback document.
        Returns the absolute filesystem path of the generated PDF.
        """
        data = profile or {}
        candidate_name = data.get("full_name") or data.get("name") or "Aarav Sharma"
        country = data.get("citizenship_country") or "India"
        address = data.get("address") or "Flat 402, Green Glen Layout, Bellandur, Bengaluru 560103"
        pan = data.get("foreign_tax_id") or data.get("pan") or "ABCDE1234F"
        dob = data.get("date_of_birth") or "10-24-1996"

        if not filename:
            unique_suffix = uuid.uuid4().hex[:8]
            clean_name = candidate_name.lower().replace(" ", "_")
            filename = f"w8ben_{clean_name}_{unique_suffix}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "W8Title",
            parent=styles["Heading1"],
            fontSize=14,
            leading=18,
            textColor=colors.black,
            alignment=1,  # Center
        )
        subtitle_style = ParagraphStyle(
            "W8Sub",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            alignment=1,
            spaceAfter=8,
        )
        section_style = ParagraphStyle(
            "W8Sec",
            parent=styles["Heading3"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=6,
            spaceAfter=4,
        )
        cell_style = ParagraphStyle(
            "W8Cell",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
        )

        story = []
        story.append(Paragraph("<b>Form W-8BEN</b>", title_style))
        story.append(Paragraph("Certificate of Foreign Status of Beneficial Owner for United States Tax Withholding and Reporting (Individuals)", subtitle_style))
        story.append(Spacer(1, 4))

        # Part I
        story.append(Paragraph("<b>Part I: Identification of Beneficial Owner</b>", section_style))

        table_data = [
            [
                Paragraph("<b>1. Name of individual who is the beneficial owner:</b><br/>" + candidate_name, cell_style),
                Paragraph("<b>2. Country of citizenship:</b><br/>" + country, cell_style),
            ],
            [
                Paragraph("<b>3. Permanent residence address:</b><br/>" + address, cell_style),
                Paragraph("<b>4. Mailing address:</b><br/>Same as permanent address", cell_style),
            ],
            [
                Paragraph("<b>6a. Foreign tax identifying number (FTIN / PAN):</b><br/><b>" + pan + "</b>", cell_style),
                Paragraph("<b>6b. Check if FTIN not legally required:</b><br/>[ ] (NOT CHECKED - PAN ISSUED)", cell_style),
            ],
            [
                Paragraph("<b>8. Date of birth (MM-DD-YYYY):</b><br/>" + dob, cell_style),
                Paragraph("<b>7. Reference number(s):</b><br/>N/A", cell_style),
            ],
        ]

        t = Table(table_data, colWidths=[270, 270])
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

        # Part II
        story.append(Paragraph("<b>Part II: Claim of Tax Treaty Benefits (for chapter 3 purposes only)</b>", section_style))
        treaty_text = (
            f"<b>9.</b> I certify that the beneficial owner is a resident of <b>{country}</b> within the meaning of the income tax treaty between the United States and that country.<br/>"
            f"<b>10. Special rates and conditions:</b> The beneficial owner is claiming the provisions of <b>Article 12(2)</b> of the treaty identified on line 9 to claim a <b>15%</b> rate of withholding on (type of income): <b>Royalties / Fees for Technical Services (FTS)</b>."
        )
        story.append(Paragraph(treaty_text, cell_style))
        story.append(Spacer(1, 6))

        # Part III
        story.append(Paragraph("<b>Part III: Certification</b>", section_style))
        cert_text = (
            "Under penalties of perjury, I declare that I have examined the information on this form and to the best of my knowledge and belief it is true, correct, and complete.<br/><br/>"
            f"<b>Sign Here:</b> <i>{candidate_name}</i> &nbsp;&nbsp;&nbsp;&nbsp; <b>Capacity:</b> Self"
        )
        story.append(Paragraph(cert_text, cell_style))

        doc.build(story)
        return os.path.abspath(filepath)


# Convenience singleton
_generator = SyntheticDocumentGenerator()


def generate_synthetic_resume(profile: Optional[Dict[str, Any]] = None, output_path: Optional[str] = None) -> str:
    """Convenience helper to generate a synthetic resume."""
    return _generator.generate_resume(profile=profile, filename=os.path.basename(output_path) if output_path else None)


def generate_synthetic_w8ben(profile: Optional[Dict[str, Any]] = None, output_path: Optional[str] = None) -> str:
    """Convenience helper to generate a synthetic W-8BEN tax form."""
    return _generator.generate_tax_document(profile=profile, filename=os.path.basename(output_path) if output_path else None)
