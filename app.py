import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import cv2
import numpy as np
import re
import spacy
import tempfile
import io
import os
import pandas as pd

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Optional (Windows): set tesseract path
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------- OCR Helper ----------------
def preprocess_image_for_ocr(pil_img):
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.threshold(gray, 0, 255,
                         cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return Image.fromarray(gray)

# ---------------- PDF Text Extraction ----------------
def extract_full_text(pdf_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_file.read())
        tmp_path = tmp.name
    text = ""
    try:
        doc = fitz.open(tmp_path)
        for page in doc:
            ptxt = page.get_text()
            if ptxt.strip():
                text += ptxt + "\n"
        doc.close()
        # OCR fallback
        if len(text.strip()) < 20:
            text = ""
            doc = fitz.open(tmp_path)
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes()))
                img = preprocess_image_for_ocr(img)
                text += pytesseract.image_to_string(img) + "\n"
            doc.close()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return text

# ---------------- Document Type Detection ----------------
def get_doc_type(text):
    t = text.lower()
    if "aadhaar" in t or re.search(r"\d{4}\s\d{4}\s\d{4}", t):
        return "Aadhaar Card"
    elif "permanent account" in t or re.search(r"[A-Z]{5}[0-9]{4}[A-Z]",
                                               t, re.IGNORECASE):
        return "PAN Card"
    elif "passport" in t or "p<" in t:
        return "Passport"
    elif "marks memo" in t or "ssc" in t or "intermediate" in t or "diploma" in t:
        return "Marks Memo"
    elif "degree" in t or "b.tech" in t:
        return "Degree Certificate"
    else:
        return "Unknown Document"

# ---------------- Name Extraction ----------------
def extract_name_from_text(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if re.search(r'\bname\b', line.lower()) and not any(
                k in line.lower() for k in ["father", "mother", "s/o", "d/o", "c/o"]):
            name_line = re.sub(r'(?i)name\s*[:\-]?', '', line).strip()
            if re.match(r'^[A-Za-z ]+$', name_line) and len(name_line.split()) >= 2:
                parts = name_line.split()
                return " ".join(parts[:-1]), parts[-1]
    for line in lines:
        if re.match(r'^[A-Za-z ]+$', line) and len(line.split()) >= 2:
            parts = line.split()
            return " ".join(parts[:-1]), parts[-1]
    return None, None

# ---------------- Number Extraction ----------------
def extract_pan_number(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pan_regex = r"\b([A-Z]{5}[0-9]{4}[A-Z])\b"
    pan_regex_lenient = r"\b([A-Z0-9]{5}[0-9OIlZ]{4}[A-Z0-9])\b"
    for line in lines:
        if m := re.search(pan_regex, line):
            return m.group(1)
        if m2 := re.search(pan_regex_lenient, line):
            p = m2.group(1)
            p_corr = p[:5] + p[5:9].replace('O','0').replace('I','1').replace('Z','2') + p[9:]
            if re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", p_corr):
                return p_corr
    # whole text fallback
    if m := re.search(pan_regex, text):
        return m.group(1)
    if m2 := re.search(pan_regex_lenient, text):
        p = m2.group(1)
        p_corr = p[:5] + p[5:9].replace('O','0').replace('I','1').replace('Z','2') + p[9:]
        if re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", p_corr):
            return p_corr
    return None

def extract_aadhaar_number(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    aadhaar_regex = r"\b([2-9][0-9]{3}\s[0-9]{4}\s[0-9]{4})\b"
    aadhaar_regex_lenient = r"\b([2-9OIlZ][0-9OIlZ]{3}\s?[0-9OIlZ]{4}\s?[0-9OIlZ]{4})\b"
    for line in lines:
        if m := re.search(aadhaar_regex, line):
            return m.group(1)
        if m2 := re.search(aadhaar_regex_lenient, line):
            a = m2.group(1).replace(" ", "")
            a_corr = a.replace("O","0").replace("I","1").replace("Z","2")
            if re.match(r"^[2-9][0-9]{11}$", a_corr):
                return f"{a_corr[:4]} {a_corr[4:8]} {a_corr[8:]}"
    # whole text
    if m := re.search(aadhaar_regex, text):
        return m.group(1)
    if m2 := re.search(aadhaar_regex_lenient, text):
        a = m2.group(1).replace(" ", "")
        a_corr = a.replace("O","0").replace("I","1").replace("Z","2")
        if re.match(r"^[2-9][0-9]{11}$", a_corr):
            return f"{a_corr[:4]} {a_corr[4:8]} {a_corr[8:]}"
    return None

def extract_passport_number(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pass_regex_strict = r"\b([A-Z][0-9]{7})\b"
    pass_regex_lenient = r"\b([A-Z0-9][0-9OIlZ]{7})\b"
    for line in lines:
        if m := re.search(pass_regex_strict, line):
            return m.group(1)
        if m2 := re.search(pass_regex_lenient, line):
            p = m2.group(1)
            p_corr = p[0] + p[1:].replace("O","0").replace("I","1").replace("Z","2")
            if re.match(r"^[A-Z][0-9]{7}$", p_corr):
                return p_corr
    # MRZ fallback
    if mrz_match := re.search(r"P<\w{3}([A-Z<]+)<<([A-Z<]+).*?([A-Z0-9OIlZ]{8,9})",
                               text.replace("\n", "")):
        raw_num = mrz_match.group(3)
        return raw_num.replace("O","0").replace("I","1").replace("Z","2")
    return None

# ---------------- Field Parsing ----------------
def parse_fields(text, doc_type):
    first_name, last_name = extract_name_from_text(text)
    if not first_name:
        doc = nlp(text)
        persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"
                   and re.match(r'^[A-Za-z ]+$', ent.text)]
        if persons:
            parts = persons[0].split()
            if len(parts) >= 2:
                first_name, last_name = " ".join(parts[:-1]), parts[-1]
    # DOB
    dob = None
    if dob_match := re.search(r'(Date of Birth|DOB)\s*[:\-]?\s*'
                              r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.IGNORECASE):
        dob = dob_match.group(2)
    else:
        doc = nlp(text)
        dates = [ent.text for ent in doc.ents if ent.label_ == "DATE" and re.search(r"\d", ent.text)]
        if dates:
            dob = dates[0]
    # Year
    year = None
    if year_match := re.search(r'(Year of Passing|Passed Out|Pass out Year)\s*[:\-]?\s*(\d{4})',
                               text, re.IGNORECASE):
        year = year_match.group(2)
    # Doc num
    doc_num = None
    if doc_type == "Aadhaar Card":
        doc_num = extract_aadhaar_number(text)
    elif doc_type == "PAN Card":
        doc_num = extract_pan_number(text)
    elif doc_type == "Passport":
        doc_num = extract_passport_number(text)
    return first_name, last_name, dob, year, doc_num

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Document Data Extractor", layout="centered")
st.title("📄 Smart Document Data Extractor")

pdf_file = st.file_uploader("Upload your PDF document", type=["pdf"])
if pdf_file:
    with st.spinner("Extracting text..."):
        full_text = extract_full_text(pdf_file)
    if not full_text.strip():
        st.error("❌ No text extracted from PDF.")
    else:
        doc_type = get_doc_type(full_text)
        first_name, last_name, dob, year, doc_num = parse_fields(full_text, doc_type)

        def display_val(val): return val if val else "❌ Not Found"

        table_data = [
            ["First Name", display_val(first_name)],
            ["Last Name", display_val(last_name)],
            ["Date of Birth", display_val(dob)]
        ]
        if doc_type in ["Marks Memo", "Degree Certificate"]:
            table_data.append(["Passed-Out Year", display_val(year)])
        elif doc_type == "Aadhaar Card":
            table_data.append(["Aadhaar Number", display_val(doc_num)])
        elif doc_type == "PAN Card":
            table_data.append(["PAN Number", display_val(doc_num)])
        elif doc_type == "Passport":
            table_data.append(["Passport Number", display_val(doc_num)])

        st.success(f"✅ Document Type: {doc_type}")
        st.subheader("📋 Extracted Information")
        st.table(pd.DataFrame(table_data, columns=["Field", "Value"]))

        with st.expander("📜 Show Raw Extracted Text"):
            st.text_area("Extracted Text", full_text, height=300)
