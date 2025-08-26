import streamlit as st
import google.generativeai as genai
import json, re
import pandas as pd
from io import BytesIO

# -------------------------------
# Configure Gemini API
# -------------------------------
genai.configure(api_key="AIzaSyA7elBt6OV5CHgghLBdBEr1cjVBaGPn9hw")
model = genai.GenerativeModel("gemini-1.5-flash")

st.set_page_config(page_title="PDF Document Parser", page_icon="📑")
st.title("📑 Smart PDF Document Parser")
st.write("Upload multiple Aadhaar, PAN, Passport, or Study Certificates (PDF). "
         "The app detects the type and extracts fields, then lets you download Excel/CSV.")

# Allow multiple uploads
uploaded_pdfs = st.file_uploader("Upload your documents (PDF only)", type=["pdf"], accept_multiple_files=True)

# -------------------------------
# Helper: extract clean JSON
# -------------------------------
def extract_json_block(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    start = text.find("{")
    if start == -1:
        return None
    cnt = 0; in_str = False; esc = False
    for i, ch in enumerate(text[start:], start=start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                cnt += 1
            elif ch == "}":
                cnt -= 1
                if cnt == 0:
                    return text[start:i+1]
    return None

# -------------------------------
# Prompt for Gemini
# -------------------------------
prompt = """
You are an intelligent document parser.
Identify the type of document in the uploaded PDF (Aadhaar, PAN, Passport, or Study Certificate).
Then extract the following fields:

- Aadhaar Card → Name, DOB, Aadhaar Number  
- PAN Card → Name, DOB, PAN Number  
- Passport → Name, Passport Number, Nationality, DOB, Expiry Date  
- Study Certificate → Student Name, Course, College/University, Passout Year  

Return ONLY a single valid JSON object. Example:
{
  "document_type": "PAN",
  "extracted_fields": {
     "Name": "John Doe",
     "DOB": "01-01-1990",
     "PAN Number": "ABCDE1234F"
  }
}
"""

# -------------------------------
# Column mapping per document type
# -------------------------------
doc_columns = {
    "Aadhaar": ["document_type", "Name", "DOB", "Aadhaar Number", "source_file"],
    "PAN": ["document_type", "Name", "DOB", "PAN Number", "source_file"],
    "Passport": ["document_type", "Name", "Passport Number", "Nationality", "DOB", "Expiry Date", "source_file"],
    "Study Certificate": ["document_type", "Student Name", "Course", "College/University", "Passout Year", "source_file"],
}

# -------------------------------
# Main processing
# -------------------------------
if uploaded_pdfs and st.button("Extract All Details"):
    results = []
    with st.spinner("Analyzing all PDFs..."):
        for pdf in uploaded_pdfs:
            try:
                pdf_data = pdf.read()
                response = model.generate_content(
                    [prompt, {"mime_type": "application/pdf", "data": pdf_data}]
                )
                raw = (response.text or "").strip()
                candidate = extract_json_block(raw) or raw
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                data = json.loads(candidate)

                # Flatten JSON for tabular form
                if isinstance(data, dict):
                    if isinstance(data.get("extracted_fields"), dict):
                        flat = {"document_type": data.get("document_type", "")}
                        flat.update(data["extracted_fields"])
                    elif isinstance(data.get("extracted_data"), dict):
                        flat = {"document_type": data.get("document_type", "")}
                        flat.update(data["extracted_data"])
                    else:
                        flat = data
                else:
                    flat = {"result": str(data)}

                flat["source_file"] = pdf.name
                results.append(flat)

            except Exception as e:
                results.append({"source_file": pdf.name, "error": str(e)})

    # Convert to DataFrame
    df = pd.DataFrame(results)
    st.success("✅ All documents parsed")
    st.dataframe(df)

    # -------------------------------
    # Excel download (multi-sheet, filtered columns)
    # -------------------------------
    xbuf = BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
        for doc_type, group in df.groupby("document_type"):
            safe_sheet_name = str(doc_type)[:31] or "Unknown"

            # Apply column filter if defined
            if doc_type in doc_columns:
                cols = [c for c in doc_columns[doc_type] if c in group.columns]
                group = group[cols]

            group.to_excel(writer, index=False, sheet_name=safe_sheet_name)

    xbuf.seek(0)

    st.download_button(
        label="📥 Download Excel",
        data=xbuf,
        file_name="parsed_document.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
