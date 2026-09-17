"""Regenerate safe, fictional text-resume fixtures. No external service needed."""

from pathlib import Path
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1] / "demo"
ROOT.mkdir(exist_ok=True)
lines = [
    "Alex Morgan",
    "Education",
    "New York University, BSc Finance, 2024",
    "Experience",
    "Finance intern at a fictional advisory firm. Built valuation models.",
    "Skills",
    "Financial modeling, valuation, Excel, Python",
    "Sectors",
    "Investment Banking",
    "Career Goals",
    "Build a career in investment banking.",
    "Target Regions",
    "New York, London",
    "Target Roles",
    "Investment Banking Analyst",
    "Contact Purpose",
    "Learn about career paths in investment banking.",
]
doc = Document()
for line in lines:
    doc.add_paragraph(line)
doc.save(ROOT / "sample-resume.docx")
# A deliberately simple, truly text-based PDF for parser tests.
writer = PdfWriter()
page = writer.add_blank_page(width=612, height=792)
font = DictionaryObject(
    {
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }
)
page[NameObject("/Resources")] = DictionaryObject(
    {
        NameObject("/Font"): DictionaryObject(
            {NameObject("/F1"): writer._add_object(font)}
        )
    }
)
content = (
    "BT /F1 11 Tf 40 750 Td 17 TL\n"
    + "\n".join(
        "(" + line.replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines
    )
    + "\nET"
)
stream = DecodedStreamObject()
stream.set_data(content.encode())
page[NameObject("/Contents")] = writer._add_object(stream)
with (ROOT / "sample-resume.pdf").open("wb") as out:
    writer.write(out)
writer = PdfWriter()
writer.add_blank_page(width=612, height=792)
with (ROOT / "image-only.pdf").open("wb") as out:
    writer.write(out)
(ROOT / "README.md").write_text(
    "All examples are fictional. sample-resume.pdf and sample-resume.docx contain extractable text. image-only.pdf is an intentionally textless PDF that must be rejected; it simulates the no-text condition of a scan.\n"
)
print("Created resume fixtures in demo/.")
