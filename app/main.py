# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os, io, json, re, openai
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

app = FastAPI(
    title="Plagiarism Detector Tool",
    description="A MVP tool which detects student plagiarism",
    version="0.1.0",
)

# ── Azure Form Recognizer setup ───────────────────────────────────────────────
FR_ENDPOINT = "https://aifordocumentscanner.services.ai.azure.com/"
FR_KEY = "6nFe2HqtZAPM33dBa84upbMI640ntmjZfS471GcDEx9RJfBm72ljJQQJ99BGACYeBjFXJ3w3AAAAACOGuKFV"

if not FR_ENDPOINT or not FR_KEY:
    raise RuntimeError(
        "Missing FORM_RECOGNIZER_ENDPOINT or FORM_RECOGNIZER_KEY")

doc_client = DocumentAnalysisClient(
    endpoint=FR_ENDPOINT,
    credential=AzureKeyCredential(FR_KEY)
)

# ── Azure OpenAI setup ────────────────────────────────────────────────────────
openai.api_type = "azure"
openai.api_base = "https://aifordocumentscanner.openai.azure.com/"
openai.api_key = "A5KozsbQDA6AxLe2e4aolXk74oOiSh8zQG40DDdALEUW9JEaxHiLJQQJ99BGACYeBjFXJ3w3AAAAACOGjqLr"
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
DEPLOYMENT_NAME = "gpt-4o" # e.g. "gpt-4o"

if not openai.api_base or not openai.api_key or not DEPLOYMENT_NAME:
    raise RuntimeError("Missing credentials or url")

@app.post("/analyze-pdf/")
async def analyze_pdf(file: UploadFile = File(...)):
    # 1) Validate
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415, detail="Only PDF files are supported.")

    # 2) Read bytes & send to Form Recognizer
    data = await file.read()
    stream = io.BytesIO(data)
    poller = doc_client.begin_analyze_document(
        "prebuilt-document",
        stream
    )
    result = poller.result()
    context = ''.join([line.content for page in result.pages for line in page.lines])
    
    if not context:
        raise HTTPException(
            status_code=500, detail="No text extracted from PDF.")

    # 4) Prepare quiz‑generation prompt
    system_prompt = (
        "You are an expert quiz generator. "
        "Given a body of text, produce 10 multiple-choice questions (MCQs). "
        "Each question must have 4 choices labeled A, B, C, D, and specify the correct answer."
    )
    user_prompt = (
        f"Text:\n{context}\n\n"
        "Generate the quiz as a JSON array, where each element is an object with:\n"
        "  - question: string\n"
        "  - options: [\"A. ...\",\"B. ...\",\"C. ...\",\"D. ...\"]\n"
        "  - answer: one of \"A\",\"B\",\"C\",\"D\"\n"
    )

    # 5) Call Azure OpenAI
    resp = openai.ChatCompletion.create(
        engine=DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        max_tokens=3000,
        temperature=0.2,
    )
    raw = resp.choices[0].message.content
    
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)  # drop opening fence
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # 6) Parse & return
    try:
        quiz = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Failed"
        )

    return JSONResponse(status_code=200, content=quiz)
