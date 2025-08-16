import streamlit as st
import google.generativeai as genai
import json

# Configure Gemini API
genai.configure(api_key="")

# Load Gemini model
model = genai.GenerativeModel("gemini-1.5-flash")

# Streamlit UI
st.set_page_config(page_title="PDF Document Parser", page_icon="📑")
st.title("📑 Smart PDF Document Parser")

st.write("Upload Aadhaar, PAN, Passport, or Study Certificate in PDF format. The app will detect the document type and extract details automatically.")

# PDF Upload
uploaded_pdf = st.file_uploader("Upload your document (PDF only)", type=["pdf"])

if uploaded_pdf:
    st.write("📂 Uploaded file:", uploaded_pdf.name)

    # Read PDF file
    pdf_data = uploaded_pdf.read()

    # Prompt for Gemini
    prompt = """
    You are an intelligent document parser.
    Identify the type of document in the uploaded PDF (Aadhaar, PAN, Passport, or Study Certificate).
    Then extract the following fields:

    - Aadhaar Card → Name, DOB, Aadhaar Number  
    - PAN Card → Name, DOB, PAN Number  
    - Passport → Name, Passport Number, Nationality, DOB, Expiry Date  
    - Study Certificate → Student Name, Course, College/University, Passout Year  

    Return the response in strict JSON format.
    """

    if st.button("Extract Details"):
        with st.spinner("Analyzing PDF..."):
            try:
                response = model.generate_content(
                    [prompt, {"mime_type": "application/pdf", "data": pdf_data}]
                )
                
                result = response.text.strip()

                # Ensure valid JSON
                try:
                    data = json.loads(result)
                    st.success("✅ Document successfully parsed")
                    st.json(data)
                except:
                    st.error("⚠️ Could not parse JSON. Raw response:")
                    st.write(result)

            except Exception as e:
                st.error(f"Error: {e}")
