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
from typing import List, Optional

import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pdfminer.high_level import extract_text as pdf_extract

# Local ML (fallback)
from nlp import classify as local_classify
from templates import PRODUCTIVE_REPLY, NON_PRODUCTIVE_REPLY

# --------- Config HF (opcional) ----------
USE_HF_ENV = os.getenv("USE_HF") == "1"
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
USE_HF = bool(USE_HF_ENV and HF_TOKEN)  # só ativa HF se houver token

HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
HF_ZERO_SHOT_MODEL = "facebook/bart-large-mnli"
HF_T2T_MODEL = "google/flan-t5-base"  # para gerar resposta curta em PT-BR


def hf_zero_shot_productive(text: str):
    """
    Classifica Produtivo vs Improdutivo via zero-shot (BART-MNLI).
    Com fallback para o classificador local em caso de erro.
    """
    url = f"https://api-inference.huggingface.co/models/{HF_ZERO_SHOT_MODEL}"
    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": ["Produtivo", "Improdutivo"], "multi_label": False},
    }
    try:
        r = httpx.post(url, headers=HF_HEADERS, json=payload, timeout=45)
        r.raise_for_status()
        data = r.json()
        label = data["labels"][0]
        score = float(data["scores"][0])
        return label, score
    except Exception as e:
        print(f"[HF zero-shot] erro: {e}", flush=True)
        # fallback local
        return local_classify(text)


def hf_generate_reply(category: str, email_text: str) -> str:
    """
    Gera uma resposta curta, educada e em PT-BR para a categoria detectada.
    Com fallback para template em caso de erro.
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
    try:
        r = httpx.post(
            url,
            headers=HF_HEADERS,
            json={"inputs": prompt, "parameters": {"max_new_tokens": 120, "temperature": 0.2}},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        text = (data[0].get("generated_text") or "").strip()
        if text:
            return text
    except Exception as e:
        print(f"[HF generate] erro: {e}", flush=True)

    return PRODUCTIVE_REPLY if category == "Produtivo" else NON_PRODUCTIVE_REPLY


def decide_and_suggest(text: str):
    """
    Decide a categoria e produz a resposta:
      - Se USE_HF=1 (e token presente), usa HF com fallback.
      - Caso contrário, usa o classificador local + templates.
    """
    if USE_HF:
        label, conf = hf_zero_shot_productive(text)
        suggestion = hf_generate_reply(label, text)
        return label, conf, suggestion

    # modo local
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
    mode = "HF" if USE_HF else "LOCAL"
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
    return {"status": "ok", "mode": "HF" if USE_HF else "LOCAL"}


@app.post("/api/process")
async def process_emails(
    request: Request,
    files: Optional[List[UploadFile]] = File(default=None),
    text: Optional[str] = Form(default=None),
):
    results = []

    # Fallback: se não vier form-data com 'text', tente JSON {"text": "..."}
    if (not files) and (not (text and text.strip())):
        try:
            if "application/json" in (request.headers.get("content-type") or ""):
                body = await request.json()
                text = (body.get("text") or "").strip()
        except Exception:
            pass

    # 1) Texto colado
    if text and text.strip():
        label, conf, suggestion = decide_and_suggest(text)
        results.append(
            {"source": "input_text", "category": label, "confidence": conf, "suggestion": suggestion}
        )

    # 2) Arquivos
    if files:
        for f in files:
            raw = await f.read()
            filename = f.filename or "file"

            # PDF com try/except e mensagem clara
            if filename.lower().endswith(".pdf") or (f.content_type or "").lower() == "application/pdf":
                try:
                    content = pdf_extract(BytesIO(raw))
                    if not content or not content.strip():
                        raise ValueError("PDF sem texto extraível (possivelmente digitalizado ou protegido).")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Falha ao ler PDF '{filename}': {e}",
                    )
            else:
                content = read_txt_bytes(raw)

            label, conf, suggestion = decide_and_suggest(content)
            results.append(
                {"source": filename, "category": label, "confidence": conf, "suggestion": suggestion}
            )

    if not results:
        raise HTTPException(
            status_code=400,
            detail="Envie 'text' (JSON ou form-data) ou 'files' como multipart/form-data.",
        )

    return results
