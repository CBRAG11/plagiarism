# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os
import base64

app = FastAPI(
    title="Plagiarism Detector Tool",
    description="A MVP tool which detects student plagiarism",
    version="0.1.0",
)

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


