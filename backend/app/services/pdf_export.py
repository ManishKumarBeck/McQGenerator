"""Printable PDF export of a test: question paper, optional OMR answer sheet and answer key."""

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .. import schemas
from ..errors import ConflictError
from ..models import Test

logging.getLogger("fontTools").setLevel(logging.WARNING)  # font subsetting is chatty at INFO

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
LETTERS = "ABCDEF"
FONT = "DejaVu"

# Colours (RGB)
INK = (17, 24, 39)
MUTED = (92, 101, 120)
RULE = (205, 211, 223)
BRAND = (79, 70, 229)


@dataclass
class PaperQuestion:
    number: int
    text: str
    options: list[str]
    correct_option: int
    explanation: str
    source_ref: str = ""


def default_instructions(test: Test, count: int) -> str:
    lines = [
        f"This paper contains {count} multiple-choice question{'s' if count != 1 else ''}.",
        "Each question has exactly one correct answer.",
    ]
    marks = _fmt(test.marks_per_question)
    if test.negative_marks > 0:
        lines.append(
            f"Each correct answer carries {marks} mark(s); {_fmt(test.negative_marks)} mark(s) "
            "will be deducted for each wrong answer. Unanswered questions score 0."
        )
    else:
        lines.append(f"Each correct answer carries {marks} mark(s). There is no negative marking.")
    lines.append(f"Time allowed: {test.duration_minutes} minutes.")
    return "\n".join(lines)


def _fmt(value: float) -> str:
    return f"{value:g}"


def _seed(test_id: int, version: str) -> int:
    digest = hashlib.sha256(f"{test_id}:{version}".encode()).hexdigest()
    return int(digest[:12], 16)


def build_paper(test: Test, options: schemas.PdfExportOptions) -> list[PaperQuestion]:
    """Questions in paper order. Shuffling is deterministic per test + version label,
    so re-downloading "Set B" always produces the same paper and key."""
    questions = list(test.questions)
    rng = random.Random(_seed(test.id, options.version_label or "default"))
    if options.shuffle_questions:
        rng.shuffle(questions)
    paper = []
    for number, question in enumerate(questions, start=1):
        order = list(range(len(question.options)))
        if options.shuffle_options:
            rng.shuffle(order)
        paper.append(
            PaperQuestion(
                number=number,
                text=question.text,
                options=[question.options[i] for i in order],
                correct_option=order.index(question.correct_option),
                explanation=question.explanation,
                source_ref=question.source_ref,
            )
        )
    return paper


class _PaperPDF(FPDF):
    def __init__(self, footer_text: str):
        super().__init__(format="A4", unit="mm")
        self.footer_text = footer_text
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(auto=True, margin=18)
        self.add_font(FONT, "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font(FONT, "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font(FONT, "I", str(FONT_DIR / "DejaVuSans-Oblique.ttf"))
        self.alias_nb_pages()

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FONT, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, self.footer_text, align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    # ------------------------------------------------------------------ helpers

    @property
    def content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def rule(self, gap: float = 3) -> None:
        self.ln(gap / 2)
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(gap / 2)

    def text_block(
        self, text: str, size: float, style: str = "", color=INK, align="L", h: float | None = None
    ):
        self.set_font(FONT, style, size)
        self.set_text_color(*color)
        self.multi_cell(0, h or size * 0.5, text, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _header(pdf: _PaperPDF, test: Test, options: schemas.PdfExportOptions, count: int) -> None:
    if options.institution:
        pdf.text_block(options.institution, 15, "B", align="C", h=7)
    pdf.text_block(options.title or test.title, 13 if options.institution else 16, "B", BRAND, "C", h=7)
    subtitle = options.subtitle
    if subtitle:
        pdf.text_block(subtitle, 10, "", MUTED, "C", h=5)
    if options.version_label:
        pdf.text_block(f"Paper version: {options.version_label}", 9, "B", MUTED, "C", h=5)
    pdf.ln(1)

    if options.show_details:
        pdf.rule(2)
        parts = []
        if options.exam_date:
            parts.append(f"Date: {options.exam_date}")
        parts.append(f"Time: {test.duration_minutes} min")
        parts.append(f"Questions: {count}")
        parts.append(f"Maximum marks: {_fmt(test.marks_per_question * count)}")
        pdf.text_block("     |     ".join(parts), 9.5, "", INK, "C", h=5.5)
        marking = f"Marking: +{_fmt(test.marks_per_question)} per correct answer"
        marking += (
            f", −{_fmt(test.negative_marks)} per wrong answer"
            if test.negative_marks > 0
            else ", no negative marking"
        )
        pdf.text_block(marking + ", 0 if unanswered", 9, "", MUTED, "C", h=5)
    pdf.rule(3)

    if options.student_fields:
        _student_fields(pdf)

    instructions = options.instructions.strip()
    if instructions:
        pdf.set_font(FONT, "B", 10)
        pdf.set_text_color(*INK)
        pdf.cell(0, 6, "Instructions", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(FONT, "", 9)
        pdf.set_text_color(*MUTED)
        for number, line in enumerate((ln for ln in instructions.splitlines() if ln.strip()), start=1):
            pdf.set_x(pdf.l_margin + 2)
            pdf.multi_cell(
                pdf.content_width - 2,
                4.6,
                f"{number}. {line.strip()}",
                align="L",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        pdf.rule(5)


def _student_fields(pdf: _PaperPDF) -> None:
    pdf.set_font(FONT, "", 10)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*MUTED)
    pdf.set_line_width(0.25)
    y = pdf.get_y() + 3
    col = pdf.content_width / 3
    for i, label in enumerate(("Name", "Roll No.", "Signature")):
        x = pdf.l_margin + i * col
        pdf.set_xy(x, y)
        pdf.cell(pdf.get_string_width(label + ": ") + 1, 6, f"{label}:")
        pdf.line(pdf.get_x(), y + 5.2, x + col - 4, y + 5.2)
    pdf.set_xy(pdf.l_margin, y + 10)


def _options_fit_two_columns(pdf: _PaperPDF, options: list[str]) -> bool:
    pdf.set_font(FONT, "", 10)
    half = (pdf.content_width - 8) / 2 - 10
    return len(options) % 2 == 0 and all(pdf.get_string_width(o) <= half for o in options)


def _draw_question(doc: _PaperPDF, q: PaperQuestion) -> None:
    indent = 8
    doc.set_font(FONT, "B", 10.5)
    doc.set_text_color(*INK)
    y = doc.get_y()
    doc.cell(indent, 5.6, f"{q.number}.")
    doc.set_xy(doc.l_margin + indent, y)
    doc.set_font(FONT, "", 10.5)
    doc.multi_cell(doc.content_width - indent, 5.6, q.text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(1)
    doc.set_font(FONT, "", 10)
    if _options_fit_two_columns(doc, q.options):
        col = (doc.content_width - indent) / 2
        for row in range(0, len(q.options), 2):
            y = doc.get_y()
            for offset in (0, 1):
                i = row + offset
                doc.set_xy(doc.l_margin + indent + offset * col, y)
                doc.cell(col, 5.6, f"({LETTERS[i]})  {q.options[i]}")
            doc.set_xy(doc.l_margin, y + 6)
    else:
        for i, option in enumerate(q.options):
            doc.set_x(doc.l_margin + indent)
            doc.multi_cell(
                doc.content_width - indent,
                5.4,
                f"({LETTERS[i]})  {option}",
                align="L",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            doc.ln(0.6)
    doc.ln(4)


def _question(pdf: _PaperPDF, q: PaperQuestion) -> None:
    """Draw a question, moving it to a new page rather than splitting it across pages."""
    with pdf.offset_rendering() as trial:
        _draw_question(trial, q)
    if trial.page_break_triggered:
        pdf.add_page()
    _draw_question(pdf, q)


def _answer_sheet(pdf: _PaperPDF, paper: list[PaperQuestion], title: str, student_fields: bool) -> None:
    pdf.add_page()
    pdf.text_block("Answer Sheet", 14, "B", BRAND, "C", h=7)
    pdf.text_block(title, 10, "", MUTED, "C", h=5)
    pdf.text_block("Fill in one circle per question completely.", 9, "I", MUTED, "C", h=5)
    pdf.rule(4)
    if student_fields:
        _student_fields(pdf)
        pdf.rule(3)

    columns = 3
    col_width = pdf.content_width / columns
    row_h = 7.2
    radius = 2.3
    top = pdf.get_y() + 2
    index = 0
    while index < len(paper):
        if index:
            pdf.add_page()
            top = pdf.t_margin + 4
        rows_fit = max(1, int((pdf.h - pdf.b_margin - top) // row_h))
        remaining = len(paper) - index
        # Balance the columns instead of filling the first one completely.
        rows_per_col = min(rows_fit, -(-remaining // columns))
        chunk = paper[index : index + rows_per_col * columns]
        for slot, q in enumerate(chunk):
            col, row = divmod(slot, rows_per_col)
            _bubble_row(pdf, q, pdf.l_margin + col * col_width, top + row * row_h, radius)
        index += len(chunk)


def _bubble_row(pdf: _PaperPDF, q: PaperQuestion, x: float, y: float, radius: float) -> None:
    pdf.set_font(FONT, "B", 9)
    pdf.set_text_color(*INK)
    pdf.set_xy(x, y)
    pdf.cell(9, 5, f"{q.number}.", align="R")
    pdf.set_draw_color(*MUTED)
    pdf.set_line_width(0.25)
    pdf.set_font(FONT, "", 6.5)
    for i in range(len(q.options)):
        cx = x + 15 + i * 7
        cy = y + 2.5
        pdf.circle(cx, cy, radius)
        pdf.set_xy(cx - radius, cy - 1.6)
        pdf.cell(radius * 2, 3.2, LETTERS[i], align="C")


def _answer_key(pdf: _PaperPDF, paper: list[PaperQuestion], title: str, explanations: bool) -> None:
    pdf.add_page()
    pdf.text_block("Answer Key", 14, "B", BRAND, "C", h=7)
    pdf.text_block(title, 10, "", MUTED, "C", h=5)
    pdf.rule(4)

    # Compact grid of answers: "12.  B"
    per_row = 8
    cell_w = pdf.content_width / per_row
    pdf.set_text_color(*INK)
    for start in range(0, len(paper), per_row):
        for q in paper[start : start + per_row]:
            pdf.set_font(FONT, "", 10)
            pdf.cell(cell_w * 0.5, 7, f"{q.number}.", align="R")
            pdf.set_font(FONT, "B", 10)
            pdf.cell(cell_w * 0.5, 7, f"  {LETTERS[q.correct_option]}")
        pdf.ln(7)

    if explanations and any(q.explanation or q.source_ref for q in paper):
        pdf.rule(6)
        pdf.text_block("Explanations", 11, "B", INK, h=6)
        pdf.ln(1)
        for q in paper:
            if not (q.explanation or q.source_ref):
                continue
            with pdf.unbreakable() as doc:
                doc.set_font(FONT, "B", 9.5)
                doc.set_text_color(*INK)
                answer = q.options[q.correct_option]
                doc.multi_cell(
                    0,
                    5,
                    f"{q.number}. ({LETTERS[q.correct_option]}) {answer}",
                    align="L",
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
                doc.set_font(FONT, "", 9)
                doc.set_text_color(*MUTED)
                doc.set_x(doc.l_margin + 5)
                note = q.explanation
                if q.source_ref:
                    note = f"{note} (Source: {q.source_ref})" if note else f"Source: {q.source_ref}"
                doc.multi_cell(
                    doc.content_width - 5, 4.6, note, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )
                doc.ln(2.5)


def default_options(test: Test) -> schemas.PdfExportOptions:
    subtitle = " · ".join(part for part in (test.subject, test.topic, test.category) if part)
    return schemas.PdfExportOptions(
        title=test.title,
        subtitle=subtitle[:200],
        instructions=default_instructions(test, len(test.questions)),
    )


def render_test_pdf(test: Test, options: schemas.PdfExportOptions) -> bytes:
    if not test.questions:
        raise ConflictError("Add at least one question before downloading a PDF.", code="test_empty")

    paper = build_paper(test, options)
    title = options.title or test.title
    footer = title if not options.version_label else f"{title} · {options.version_label}"
    pdf = _PaperPDF(footer_text=footer[:90])
    pdf.set_title(title)
    pdf.set_author(options.institution or "McqGen")
    pdf.set_creator("McqGen")

    heading = title if not options.version_label else f"{title} · {options.version_label}"
    pdf.add_page()
    _header(pdf, test, options, len(paper))
    for question in paper:
        _question(pdf, question)

    if options.include_answer_sheet:
        _answer_sheet(pdf, paper, heading, options.student_fields)
    if options.include_answer_key:
        _answer_key(pdf, paper, heading, options.include_explanations)
    return bytes(pdf.output())


def pdf_filename(test: Test, options: schemas.PdfExportOptions) -> str:
    base = "".join(c if c.isascii() and c.isalnum() else "-" for c in (options.title or test.title).lower())
    base = "-".join(part for part in base.split("-") if part)[:60] or "test"
    if options.version_label:
        base += "-" + "".join(c for c in options.version_label.lower() if c.isascii() and c.isalnum())[:10]
    return f"{base}-{date.today().isoformat()}.pdf"
