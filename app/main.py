# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import io
import json
import re
import openai
import httpx
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from .models import AssignQuizRequest, AssignQuizResponse
from datetime import datetime, timedelta

load_dotenv()

app = FastAPI(
    title="Plagiarism Detector Tool",
    description="A MVP tool which detects student plagiarism",
    version="0.1.0",
)

# ── Azure Form Recognizer setup ───────────────────────────────────────────────
FR_ENDPOINT = os.getenv("FR_ENDPOINT")
FR_KEY = os.getenv("FR_KEY")

if not FR_ENDPOINT or not FR_KEY:
    raise RuntimeError(
        "Missing FORM_RECOGNIZER_ENDPOINT or FORM_RECOGNIZER_KEY")

doc_client = DocumentAnalysisClient(
    endpoint=FR_ENDPOINT,
    credential=AzureKeyCredential(FR_KEY)
)

# ── Azure OpenAI setup ────────────────────────────────────────────────────────
openai.api_type = "azure"
openai.api_base = os.getenv("OPENAI_BASE")
openai.api_key = os.getenv("OPENAI_KEY")
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
DEPLOYMENT_NAME = "gpt-4o"  # e.g. "gpt-4o"

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
    context = ''.join(
        [line.content for page in result.pages for line in page.lines])

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

CANVAS_BASE_URL = os.getenv("CANVAS_API_URL")
CANVAS_TOKEN = os.getenv("CANVAS_API_TOKEN")

if not CANVAS_BASE_URL or not CANVAS_TOKEN:
    raise RuntimeError("Please set CANVAS_API_URL & CANVAS_API_TOKEN env vars")

HEADERS = {
    "Authorization": f"Bearer {CANVAS_TOKEN}",
    "Content-Type":  "application/json"
}


@app.post("/canvas/assign-quiz/", response_model=AssignQuizResponse, summary="Create a graded quiz and add MCQs")
async def assign_quiz(req: AssignQuizRequest):
    # 1) Create the Quiz
    title = f"Authorship Verification for {req.submission_id}"
    due_at = (datetime.utcnow() + timedelta(hours=24)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(due_at)
    quiz_payload = {
        "quiz": {
            "title": title,
            "quiz_type": "assignment",
            "due_at": due_at,
            "points_possible": 10
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CANVAS_BASE_URL}/api/v1/courses/{req.course_id}/quizzes",
            json=quiz_payload,
            headers=HEADERS,
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create quiz: {resp.status_code} {resp.text}"
        )
    quiz_id = resp.json()["id"]

    # 2) Add each MCQ
    created = 0
    async with httpx.AsyncClient() as client:
        for q in req.questions:
            # build the answers array
            answers = []
            for opt in q.options:
                # split "A. text"
                label, text = opt.split(".", 1)
                answers.append({
                    "text": text.strip(),
                    "weight": 1 if label.strip().lower() == q.answer.lower() else 0
                })
            question_payload = {
                "question": {
                    "question_type":     "multiple_choice_question",
                    "question_text":     q.question_text,
                    "answers":           answers,
                    "neutral_comments":  q.explanation,
                    "points_possible" : 1
                }
            }
            r2 = await client.post(
                f"{CANVAS_BASE_URL}/api/v1/courses/{req.course_id}"
                f"/quizzes/{quiz_id}/questions",
                json=question_payload,
                headers=HEADERS,
            )
            
            created += 1

    return AssignQuizResponse(quiz_id=quiz_id, created_questions=created)
