from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pdfminer.high_level import extract_text as pdf_extract
from nlp import classify
from templates import PRODUCTIVE_REPLY, NON_PRODUCTIVE_REPLY

app = FastAPI(title="Email Classifier API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def read_txt_bytes(b: bytes) -> str:
    try:
        return b.decode('utf-8', errors='ignore')
    except:
        return b.decode('latin-1', errors='ignore')

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/process")
async def process_emails(files: List[UploadFile] = File(default=[]), text: str = Form(default="")):
    results = []

    # 1) Texto colado
    if text.strip():
        label, conf = classify(text)
        suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY
        results.append({
            "source": "input_text",
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })

    for f in files:
        content = ""
        data = await f.read()

        if f.filename.lower().endswith(".pdf"):
            try:
                content = pdf_extract(f.file)  
            except:
                from io import BytesIO
                content = pdf_extract(BytesIO(data))
        else:
            content = read_txt_bytes(data)

        label, conf = classify(content)
        suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY

        results.append({
            "source": f.filename,
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })

    return results
