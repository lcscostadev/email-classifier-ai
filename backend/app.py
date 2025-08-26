# from fastapi import FastAPI, UploadFile, File, Form
# from fastapi.middleware.cors import CORSMiddleware
# from typing import List
# from pdfminer.high_level import extract_text as pdf_extract
# from nlp import classify
# from templates import PRODUCTIVE_REPLY, NON_PRODUCTIVE_REPLY

# app = FastAPI(title="Email Classifier API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# def read_txt_bytes(b: bytes) -> str:
#     try:
#         return b.decode('utf-8', errors='ignore')
#     except:
#         return b.decode('latin-1', errors='ignore')

# @app.get("/api/health")
# def health():
#     return {"status": "ok"}

# @app.post("/api/process")
# async def process_emails(files: List[UploadFile] = File(default=[]), text: str = Form(default="")):
#     results = []

#     # 1) Texto colado
#     if text.strip():
#         label, conf = classify(text)
#         suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY
#         results.append({
#             "source": "input_text",
#             "category": label,
#             "confidence": conf,
#             "suggestion": suggestion
#         })

#     for f in files:
#         content = ""
#         data = await f.read()

#         if f.filename.lower().endswith(".pdf"):
#             try:
#                 content = pdf_extract(f.file)  
#             except:
#                 from io import BytesIO
#                 content = pdf_extract(BytesIO(data))
#         else:
#             content = read_txt_bytes(data)

#         label, conf = classify(content)
#         suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY

#         results.append({
#             "source": f.filename,
#             "category": label,
#             "confidence": conf,
#             "suggestion": suggestion
#         })

#     return results


import os
from io import BytesIO
from typing import List

import httpx
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pdfminer.high_level import extract_text as pdf_extract

# Local ML (fallback)
from nlp import classify as local_classify
from templates import PRODUCTIVE_REPLY, NON_PRODUCTIVE_REPLY

# --------- Config HF (opcional) ----------
USE_HF = os.getenv("USE_HF") == "1"
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}

# Modelos públicos (gratuitos) para inference
HF_ZERO_SHOT_MODEL = "facebook/bart-large-mnli"
HF_T2T_MODEL = "google/flan-t5-base"  # para gerar resposta curta em PT-BR


def hf_zero_shot_productive(text: str):
    """
    Classifica Produtivo vs Improdutivo via zero-shot (BART-MNLI).
    """
    url = f"https://api-inference.huggingface.co/models/{HF_ZERO_SHOT_MODEL}"
    payload = {
        "inputs": text,
        "parameters": {
            "candidate_labels": ["Produtivo", "Improdutivo"],
            "multi_label": False
        }
    }
    r = httpx.post(url, headers=HF_HEADERS, json=payload, timeout=45)
    r.raise_for_status()
    data = r.json()
    # Ex.: {'labels': ['Produtivo','Improdutivo',...], 'scores': [0.91,0.09,...]}
    label = data["labels"][0]
    score = float(data["scores"][0])
    return label, score


def hf_generate_reply(category: str, email_text: str) -> str:
    """
    Gera uma resposta curta, educada e em PT-BR para a categoria detectada.
    """
    url = f"https://api-inference.huggingface.co/models/{HF_T2T_MODEL}"
    prompt = (
        "Você é um assistente de suporte ao cliente de uma empresa financeira.\n"
        f"Categoria do email: {category}\n"
        "Objetivo: redigir uma resposta breve, educada e clara em português do Brasil.\n"
        "- Se for Produtivo: confirme recebimento, explique próximo passo e prazo curto.\n"
        "- Se for Improdutivo: agradeça e informe que não é necessária ação.\n\n"
        f"Email do cliente:\n\"{email_text}\"\n\n"
        "Resposta:"
    )
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 120, "temperature": 0.2}
    }
    r = httpx.post(url, headers=HF_HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    try:
        # formato comum em text2text
        return data[0]["generated_text"].strip()
    except Exception:
        return (
            PRODUCTIVE_REPLY
            if category == "Produtivo"
            else NON_PRODUCTIVE_REPLY
        )


def decide_and_suggest(text: str):
    """
    Decide a categoria e produz a resposta:
      - Se USE_HF=1 (e token presente), usa HF p/ classificar e gerar resposta.
      - Caso contrário, usa o classificador local + templates.
    """
    if USE_HF and HF_TOKEN:
        label, conf = hf_zero_shot_productive(text)
        suggestion = hf_generate_reply(label, text)
    else:
        label, conf = local_classify(text)
        suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY
    return label, conf, suggestion


# --------- FastAPI App ----------
app = FastAPI(title="Email Classifier API")

# Em produção, substitua allow_origins pelo domínio do seu front (Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ex.: ["https://seu-front.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def read_txt_bytes(b: bytes) -> str:
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return b.decode("latin-1", errors="ignore")


@app.get("/", response_class=HTMLResponse)
def root():
    mode = "HF" if (USE_HF and HF_TOKEN) else "LOCAL"
    return f"""
    <html>
      <head><title>Email Classifier API</title></head>
      <body style="font-family: sans-serif; max-width: 720px; margin: 40px auto;">
        <h1>Email Classifier API</h1>
        <p>API online ✅ — Modo: <strong>{mode}</strong></p>
        <ul>
          <li><a href="/api/health">/api/health</a></li>
          <li><a href="/docs">/docs</a> (Swagger)</li>
        </ul>
      </body>
    </html>
    """


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "HF" if (USE_HF and HF_TOKEN) else "LOCAL"}


@app.post("/api/process")
async def process_emails(
    files: List[UploadFile] = File(default=[]),
    text: str = Form(default="")
):
    results = []

    # 1) Texto colado
    if text.strip():
        label, conf, suggestion = decide_and_suggest(text)
        results.append({
            "source": "input_text",
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })

    # 2) Arquivos
    for f in files:
        raw = await f.read()
        filename = f.filename or "file"

        if filename.lower().endswith(".pdf"):
            # Usa sempre BytesIO(raw) — confiável em UploadFile
            content = pdf_extract(BytesIO(raw))
        else:
            content = read_txt_bytes(raw)

        label, conf, suggestion = decide_and_suggest(content)
        results.append({
            "source": filename,
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })

    return results
