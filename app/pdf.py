import os
import unicodedata
from datetime import date
from fpdf import FPDF

_WIN_FONTS = r"C:\Windows\Fonts"

_SUBS = {
    "—": "--", "–": "-",
    "‘": "'",  "’": "'",
    "“": '"',  "”": '"',
    "…": "...", " ": " ",
    "•": "-",  "−": "-",
    "®": "(R)", "©": "(C)", "™": "(TM)",
}


def _safe_latin1(text: str) -> str:
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        pass
    result = []
    for ch in text:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except UnicodeEncodeError:
            if ch in _SUBS:
                result.append(_SUBS[ch])
            else:
                nfkd = unicodedata.normalize("NFKD", ch)
                result.append(nfkd.encode("ascii", "ignore").decode("ascii") or "?")
    return "".join(result)


def _clean_body(content: str) -> str:
    """Strip AI preamble/commentary and return only letter paragraphs."""
    lines = content.splitlines()
    clean = []
    for line in lines:
        stripped = line.strip()
        # Skip delimiter lines, preamble, and note blocks
        if stripped in ("---", "---\n"):
            continue
        if stripped.startswith("---"):
            continue
        low = stripped.lower()
        if low.startswith("here is") or low.startswith("here's"):
            continue
        # Stop when AI appended "notes" commentary
        if stripped.startswith("**") and ("note" in low or "honest" in low):
            break
        clean.append(line)

    # Trim leading/trailing blank lines
    text = "\n".join(clean).strip()
    return text


def cover_letter_to_pdf(
    company: str,
    title: str,
    content: str,
    location: str = "",
    candidate_name: str = "Shreyas",
) -> bytes:
    arial_reg  = os.path.join(_WIN_FONTS, "arial.ttf")
    arial_bold = os.path.join(_WIN_FONTS, "arialbd.ttf")
    use_unicode = os.path.isfile(arial_reg) and os.path.isfile(arial_bold)

    pdf = FPDF()
    pdf.set_margins(25.4, 25.4, 25.4)
    pdf.set_auto_page_break(auto=True, margin=25.4)

    if use_unicode:
        pdf.add_font("Arial", "",  arial_reg,  uni=True)
        pdf.add_font("Arial", "B", arial_bold, uni=True)
        font = "Arial"
    else:
        font = "Helvetica"
        company  = _safe_latin1(company)
        title    = _safe_latin1(title)
        location = _safe_latin1(location)
        content  = _safe_latin1(content)

    def s(t):
        return t if use_unicode else _safe_latin1(t)

    pdf.add_page()
    line_h = 6.5

    # Date
    today_str = date.today().strftime("%B %-d, %Y") if os.name != "nt" else date.today().strftime("%B %#d, %Y")
    pdf.set_font(font, size=11)
    pdf.cell(0, line_h, s(today_str), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Company   [spaces]   Location  — same line, company left / location right
    pdf.set_font(font, "B", 11)
    y = pdf.get_y()
    pdf.cell(0, line_h, s(company), align="L", new_x="LMARGIN", new_y="NEXT")
    if location:
        pdf.set_y(y)
        pdf.cell(0, line_h, s(location), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Salutation
    pdf.set_font(font, size=11)
    pdf.cell(0, line_h, s(f"Dear {company} Talent Acquisition,"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Body — strip AI commentary, split on blank lines
    body = _clean_body(content)
    for para in [p.strip() for p in body.split("\n\n") if p.strip()]:
        pdf.multi_cell(0, line_h, s(para))
        pdf.ln(3)

    # Sign-off
    pdf.ln(4)
    pdf.cell(0, line_h, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(0, line_h, s(candidate_name), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
