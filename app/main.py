# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os
import base64
import os
import io
import json
import re
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import openai

app = FastAPI(
    title="Plagiarism Detector Tool",
    description="A MVP tool which detects student plagiarism",
    version="0.1.0",
)

# ── Azure Form Recognizer setup ───────────────────────────────────────────────
FR_ENDPOINT = "https://aifordocumentscanner.services.ai.azure.com/"
FR_KEY = ""

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
openai.api_key = ""
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
DEPLOYMENT_NAME = "gpt-4o" # e.g. "gpt-4o"

if not openai.api_base or not openai.api_key or not DEPLOYMENT_NAME:
    raise RuntimeError(
        "Missing AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, or AZURE_OPENAI_DEPLOYMENT")


# URL of your analyze endpoint
# ANALYZE_URL = os.getenv("ANALYZE_URL", "http://localhost:8000/analyze-pdf/")

@app.post("/upload-pdf/")
async def upload_pdf(file : UploadFile = File(...)):
    # only PDF allowed
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415, detail="Only PDF files are supported.")

    # Read file bytes
    data = await file.read()
    b64 = base64.b64encode(data).decode("utf-8")
    # # Forward to analyze endpoint
    # files = {"file": (file.filename, data, file.content_type)}
    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(ANALYZE_URL, files=files)

    # Return whatever the analyzer returns
    try:
        return JSONResponse(status_code=200, content={"message": b64})
    except ValueError:
        # fallback if not JSON
        return JSONResponse(status_code=500, content={"message": "Something went wrong!"})


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
    context = result.content
    
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
        max_tokens=2000,
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
            detail="LLM did not return valid JSON. Response was:\n" + raw
        )

    return JSONResponse(status_code=200, content=quiz)
