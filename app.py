import streamlit as st
import google.generativeai as genai
import json, re
import pandas as pd
from io import BytesIO

# -------------------------------
# Configure Gemini API
# -------------------------------
genai.configure(api_key="AIzaSyAuJY7wt1YV0XP9TvHvzgv4MUKdqxgvo5k")  # Replace with your API key
model = genai.GenerativeModel("gemini-1.5-flash")

st.set_page_config(page_title="PDF Document Parser", page_icon="📑")
st.title("📑 Smart PDF Document Parser")
st.write("Upload one or more PDFs. Each file may contain multiple documents "
         "(Aadhaar, PAN, Passport, Study Certificates). "
         "All parsed data will be saved to Excel with one sheet per document type.")

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
# Prompt for Gemini (multi-doc)
# -------------------------------
prompt = """
You are an intelligent document parser.
The uploaded PDF may contain MULTIPLE documents (Aadhaar, PAN, Passport, Study Certificates) inside one file.

Your tasks:
1. Detect all documents inside the PDF.
2. For each document, identify its type.
3. Extract ONLY the required fields.

Required fields:
- Aadhaar → Name, DOB, Aadhaar Number
- PAN → Name, DOB, PAN Number
- Passport → Name, Passport Number, Nationality, DOB, Expiry Date
- Study Certificate → Student Name, Course, College/University, Passout Year

Return ONLY valid JSON like this:

{
  "documents": [
    {
      "document_type": "Study Certificate",
      "extracted_fields": {
        "Student Name": "Alice",
        "Course": "B.Tech CSE",
        "College/University": "XYZ University",
        "Passout Year": "2025"
      }
    },
    {
      "document_type": "PAN",
      "extracted_fields": {
        "Name": "John Doe",
        "DOB": "01-01-1990",
        "PAN Number": "ABCDE1234F"
      }
    }
  ]
}
"""

# -------------------------------
# Column mapping per doc type
# -------------------------------
doc_columns = {
    "Aadhaar": ["document_type", "Name", "DOB", "Aadhaar Number", "source_file"],
    "PAN": ["document_type", "Name", "DOB", "PAN Number", "source_file"],
    "Passport": ["document_type", "Name", "Passport Number", "Nationality", "DOB", "Expiry Date", "source_file"],
    "Study Certificate": ["document_type", "Student Name", "Course", "College/University", "Passout Year", "source_file"],
}

# -------------------------------
# File uploader
# -------------------------------
uploaded_pdfs = st.file_uploader("Upload your documents (PDF only)", type=["pdf"], accept_multiple_files=True)

# -------------------------------
# Main processing
# -------------------------------
if uploaded_pdfs and st.button("Extract All Details"):
    results = []

    with st.spinner("Analyzing PDFs with Gemini..."):
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

                # ✅ Handle multiple docs inside one PDF
                if isinstance(data, dict) and "documents" in data:
                    for doc in data["documents"]:
                        flat = {"document_type": doc.get("document_type", "")}
                        if isinstance(doc.get("extracted_fields"), dict):
                            flat.update(doc["extracted_fields"])
                        flat["source_file"] = pdf.name
                        results.append(flat)
                else:
                    # fallback single document
                    flat = {"document_type": data.get("document_type", "")}
                    if isinstance(data.get("extracted_fields"), dict):
                        flat.update(data["extracted_fields"])
                    flat["source_file"] = pdf.name
                    results.append(flat)

            except Exception as e:
                results.append({"source_file": pdf.name, "error": str(e)})

    # Convert to DataFrame
    df = pd.DataFrame(results)
    st.success("✅ All documents parsed")
    st.dataframe(df)

    # -------------------------------
    # Excel download (multi-sheet)
    # -------------------------------
    xbuf = BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
        wrote_any = False
        if "document_type" in df.columns and not df.empty:
            for doc_type, group in df.groupby("document_type"):
                if group.empty:
                    continue
                safe_sheet_name = str(doc_type)[:31]
                if doc_type in doc_columns:
                    cols = [c for c in doc_columns[doc_type] if c in group.columns]
                    group = group.reindex(columns=cols)
                group.to_excel(writer, index=False, sheet_name=safe_sheet_name)
                wrote_any = True
        if not wrote_any:
            pd.DataFrame([{"message": "No valid data extracted"}]).to_excel(
                writer, index=False, sheet_name="Results"
            )
    xbuf.seek(0)

    st.download_button(
        label="📥 Download Excel (sheets by document type)",
        data=xbuf,
        file_name="parsed_documents_by_type.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
