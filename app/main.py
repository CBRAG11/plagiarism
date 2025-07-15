# app/main.py
from fastapi import FastAPI

app = FastAPI(
    title="My FastAPI App",
    description="A minimal FastAPI project template",
    version="0.1.0",
)


@app.get("/")
async def read_root():
    return {"message": "Hello, world!"}
