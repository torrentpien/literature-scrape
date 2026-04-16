"""
PDF text extraction using PyMuPDF.

Extracts structured text from academic PDFs, identifying sections
like abstract, introduction, methods, results, discussion, etc.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Common section heading patterns in sociology journals
SECTION_PATTERNS = [
    (r"(?i)^abstract\s*$", "abstract"),
    (r"(?i)^introduction\s*$", "introduction"),
    (r"(?i)^(?:literature\s+review|theoretical\s+(?:background|framework)|theory)\s*$", "theory"),
    (r"(?i)^(?:background|context)\s*$", "background"),
    (r"(?i)^(?:data(?:\s+and\s+methods?)?|methods?(?:\s+and\s+data)?|research\s+design|methodology|analytical?\s+(?:strategy|approach|framework))\s*$", "methods"),
    (r"(?i)^(?:measures?|variables?|operationalization)\s*$", "measures"),
    (r"(?i)^(?:results?|findings?|empirical\s+results?|analysis)\s*$", "results"),
    (r"(?i)^(?:discussion|interpretation)\s*$", "discussion"),
    (r"(?i)^(?:conclusion|concluding\s+remarks?|summary)\s*$", "conclusion"),
    (r"(?i)^(?:references?|bibliography|works?\s+cited)\s*$", "references"),
    (r"(?i)^(?:appendix|supplementary|online\s+appendix)\s*", "appendix"),
    (r"(?i)^(?:acknowledgments?|funding)\s*$", "acknowledgments"),
    (r"(?i)^(?:notes?|endnotes?|footnotes?)\s*$", "notes"),
]


@dataclass
class ExtractedPaper:
    full_text: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    page_count: int = 0
    metadata: dict = field(default_factory=dict)


def extract_text_from_pdf(pdf_path: Path) -> ExtractedPaper:
    """Extract text from a PDF, attempting to identify sections."""
    logger.info(f"Extracting text from: {pdf_path.name}")

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        return ExtractedPaper()

    paper = ExtractedPaper(page_count=len(doc))

    # Extract metadata from PDF properties
    meta = doc.metadata
    if meta:
        paper.metadata = {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
        }

    # Extract all text page by page
    pages_text = []
    for page in doc:
        text = page.get_text("text")
        pages_text.append(text)

    full_text = "\n".join(pages_text)
    paper.full_text = full_text
    doc.close()

    # Parse sections
    paper.sections = _parse_sections(full_text)

    return paper


def _parse_sections(text: str) -> dict[str, str]:
    """
    Parse text into sections based on heading patterns.
    Returns a dict of section_name -> content.
    """
    lines = text.split("\n")
    sections: dict[str, str] = {}
    current_section = "preamble"
    current_content: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_content.append("")
            continue

        # Check if this line is a section heading
        matched_section = None
        for pattern, section_name in SECTION_PATTERNS:
            if re.match(pattern, stripped):
                matched_section = section_name
                break

        # Also check for numbered section headings like "1. Introduction"
        if not matched_section:
            numbered = re.match(r"^\d+\.?\s+(.+)$", stripped)
            if numbered:
                heading_text = numbered.group(1).strip()
                for pattern, section_name in SECTION_PATTERNS:
                    if re.match(pattern, heading_text):
                        matched_section = section_name
                        break

        if matched_section:
            # Save previous section
            if current_content:
                content = "\n".join(current_content).strip()
                if content:
                    sections[current_section] = content
            current_section = matched_section
            current_content = []
        else:
            current_content.append(line)

    # Save the last section
    if current_content:
        content = "\n".join(current_content).strip()
        if content:
            sections[current_section] = content

    # Stop collecting after references
    if "references" in sections:
        pass  # Keep references but don't worry about post-reference content

    logger.info(f"  Found sections: {list(sections.keys())}")
    return sections


def get_relevant_text(paper: ExtractedPaper, max_chars: int = 30000) -> str:
    """
    Get the most relevant text for summarization.
    Prioritizes abstract, introduction, theory, methods, results, discussion, conclusion.
    Truncates to max_chars to fit within LLM context.
    """
    priority_sections = [
        "abstract", "introduction", "theory", "background",
        "methods", "measures", "results", "discussion", "conclusion",
    ]

    parts = []
    total_chars = 0

    for section in priority_sections:
        if section in paper.sections:
            content = paper.sections[section]
            header = f"\n\n## {section.upper()}\n\n"
            section_text = header + content

            if total_chars + len(section_text) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 200:  # Only add if meaningful content remains
                    parts.append(section_text[:remaining] + "\n...[truncated]")
                break

            parts.append(section_text)
            total_chars += len(section_text)

    # If no sections were found, use the full text
    if not parts:
        return paper.full_text[:max_chars]

    return "".join(parts)
