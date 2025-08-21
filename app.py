import streamlit as st
import google.generativeai as genai
import json, re
import pandas as pd
from io import BytesIO

# Configure Gemini API
genai.configure(api_key="AIzaSyA7elBt6OV5CHgghLBdBEr1cjVBaGPn9hw")
model = genai.GenerativeModel("gemini-1.5-flash")

st.set_page_config(page_title="PDF Document Parser", page_icon="📑")
st.title("📑 Smart PDF Document Parser")
st.write("Upload Aadhaar, PAN, Passport, or Study Certificate (PDF). The app detects the type and extracts fields, then lets you download Excel/CSV.")

uploaded_pdf = st.file_uploader("Upload your document (PDF only)", type=["pdf"])

# --- Helper: pull a clean JSON object out of messy text ---
def extract_json_block(text: str) -> str | None:
    if not text:
        return None
    # Prefer fenced code block ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)

    # Fallback: find first balanced {...}
    start = text.find("{")
    if start == -1:
        return None
    cnt = 0
    in_str = False
    esc = False
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

if uploaded_pdf:
    st.write("📂 Uploaded file:", uploaded_pdf.name)
    pdf_data = uploaded_pdf.read()

    prompt = """
    You are an intelligent document parser.
    Identify the type of document in the uploaded PDF (Aadhaar, PAN, Passport, or Study Certificate).
    Then extract the following fields:

    - Aadhaar Card → Name, DOB, Aadhaar Number  
    - PAN Card → Name, DOB, PAN Number  
    - Passport → Name, Passport Number, Nationality, DOB, Expiry Date  
    - Study Certificate → Student Name, Course, College/University, Passout Year  

    Return ONLY a single valid JSON object (no extra text, no markdown). Use keys:
    {
      "document_type": "<Aadhaar|PAN|Passport|Study Certificate>",
      "extracted_fields": { ... }   // or "extracted_data": { ... }
    }
    """

    if st.button("Extract Details"):
        with st.spinner("Analyzing PDF..."):
            try:
                response = model.generate_content(
                    [prompt, {"mime_type": "application/pdf", "data": pdf_data}]
                )
                raw = (response.text or "").strip()

                # Clean up and parse JSON
                candidate = extract_json_block(raw) or raw
                # Remove trailing commas if any
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

                data = json.loads(candidate)  # <-- robust parse
                st.success("✅ Document successfully parsed")
                st.json(data)

                # Flatten fields for tabular output
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

                flat["source_file"] = uploaded_pdf.name  # helpful context
                df = pd.DataFrame([flat])

                # Show table
                st.dataframe(df)

                # Excel download
                xbuf = BytesIO()
                with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Parsed Data")
                xbuf.seek(0)
                st.download_button(
                    label="📥 Download as Excel (.xlsx)",
                    data=xbuf,
                    file_name=f"parsed_{uploaded_pdf.name.rsplit('.',1)[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # CSV download
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Download as CSV (.csv)",
                    data=csv_bytes,
                    file_name=f"parsed_{uploaded_pdf.name.rsplit('.',1)[0]}.csv",
                    mime="text/csv"
                )

            except Exception as e:
                st.error(f"Error: {e}")
                st.write("Raw model response below (to help debugging):")
                st.code(raw, language="json")
