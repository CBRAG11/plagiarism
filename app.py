import streamlit as st
import requests

st.set_page_config(page_title="PDF Uploader", layout="centered")
st.title("📄 Proctorio Paper Auth Verification Tool")

# Constants
passing_threshold = 7

# Session state for persistent storage
if "questions_data" not in st.session_state:
    st.session_state.questions_data = None

if "correct_answers" not in st.session_state:
    st.session_state.correct_answers = {}

# Upload file
uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None and st.session_state.questions_data is None:
    # Show file info
    file_details = {
        "Filename": uploaded_file.name,
        "FileType": uploaded_file.type,
        "FileSize (KB)": round(len(uploaded_file.getvalue()) / 1024, 2)
    }
    st.write("### File Details", file_details)

    try:
        uploaded_file.seek(0)
        with st.spinner("Analyzing PDF..."):
            response = requests.post(
                "http://localhost:8000/analyze-pdf/",
                files={"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
            )

        if response.status_code == 200:
            st.success("✅ Analysis complete!")
            questions_data = response.json()
            st.session_state.questions_data = questions_data
            st.session_state.correct_answers = {
                idx: q["answer"] for idx, q in enumerate(questions_data)
            }
        else:
            st.error(f"❌ API Error: {response.status_code}")
            st.text(response.text)

    except Exception as e:
        st.error(f"Error reading PDF: {e}")

# If questions are ready, show the quiz
if st.session_state.questions_data:
    st.write("Correct Answers:", st.session_state.correct_answers)
    st.title("📝 Please answer a few questions to verify your solution.")

    responses = {}

    with st.form("mcq_form"):
        for idx, item in enumerate(st.session_state.questions_data):
            st.subheader(f"Q{idx + 1}: {item['question']}")
            response_selected = st.radio(
                label="Select your answer:",
                options=item["options"],
                key=f"q_{idx}"
            )
            responses[f"q_{idx}"] = response_selected

        submitted = st.form_submit_button("Submit Answers")

    if submitted:
        st.write("### Your Answers:")
        st.write(responses)
        answered_correctly = 0

        for idx_str, selected_answer in responses.items():
            idx = int(idx_str.replace("q_", ""))
            correct_answer = st.session_state.correct_answers.get(idx)
            selected_letter = selected_answer.split(".")[0].strip() if selected_answer else ""

            st.write(f"Q{idx + 1}: Selected → {selected_letter}, Correct → {correct_answer}")

            if selected_letter == correct_answer:
                answered_correctly += 1

        st.write(f"✅ Correct Answers: {answered_correctly}/{len(st.session_state.correct_answers)}")

        if answered_correctly >= passing_threshold:
            st.success("🎉 You PASSED the verification!")
        else:
            st.error("❌ You did NOT pass the verification.")
