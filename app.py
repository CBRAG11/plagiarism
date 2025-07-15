import streamlit as st
import PyPDF2
import io

st.set_page_config(page_title="PDF Uploader", layout="centered")

st.title("📄 Upload and Read PDF")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    # Show file name and size
    file_details = {
        "Filename": uploaded_file.name,
        "FileType": uploaded_file.type,
        "FileSize (KB)": round(len(uploaded_file.getvalue()) / 1024, 2)
    }
    st.write("### File Details", file_details)

    try:
        # Read PDF content
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.read()))
        st.write("### PDF Contents:")
        for i, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            st.write(f"**Page {i+1}**")
            st.text(text if text else "⚠️ No text found on this page.")
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
