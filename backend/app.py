import os
import re
from io import BytesIO
from typing import List, Optional, Union

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

# --------- Regras de negócio (saudações/boas festas) ----------
HOLIDAY_PATTERNS = [
    r"\bfeliz\s+natal\b",
    r"\bboas\s+festas\b",
    r"\bfeliz\s+ano\s+novo\b",
    r"\bbo[mn]\s+natal\b",          # "bom natal" / "bon natal" (tolerante)
    r"\bmerry\s+christmas\b",
    r"\bhappy\s+new\s+year\b",
]

def is_holiday_greeting(text: str) -> bool:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t)
    return any(re.search(p, t, flags=re.IGNORECASE) for p in HOLIDAY_PATTERNS)


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
      - Regras de negócio (curto-circuito) para saudações de fim de ano.
      - Se USE_HF=1 (e token presente), usa HF com fallback.
      - Caso contrário, usa o classificador local + templates.
    """
    # 0) Regra de curto-circuito para saudações/boas festas
    if is_holiday_greeting(text):
        label = "Improdutivo"
        conf = 0.95
        suggestion = NON_PRODUCTIVE_REPLY
        return label, conf, suggestion

    # 1) Modo HF (se ativo)
    if USE_HF:
        label, conf = hf_zero_shot_productive(text)
        suggestion = hf_generate_reply(label, text)
        return label, conf, suggestion

    # 2) Modo local
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
    # aceita 1 arquivo (UploadFile) OU múltiplos arquivos (List[UploadFile])
    file: Optional[UploadFile] = File(default=None),
    files: Optional[List[UploadFile]] = File(default=None),
    text: Optional[str] = Form(default=None),
):
    results = []

    # --- normaliza 'files' para uma lista única (file + files + files[]) ---
    files_list: List[UploadFile] = []
    if file is not None:
        files_list.append(file)
    if isinstance(files, list) and files:
        files_list.extend(files)

    # alguns clientes mandam como "files[]" ou múltiplos campos "files"
    try:
        form = await request.form()
        alt_list = form.getlist("files") or form.getlist("files[]")
        for it in alt_list:
            if isinstance(it, UploadFile):
                files_list.append(it)
    except Exception:
        pass

    # remove duplicados (mesmo objeto) e vazios (sem nome)
    dedup: List[UploadFile] = []
    seen_ids = set()
    for f in files_list:
        if not isinstance(f, UploadFile):
            continue
        if not (f.filename and f.filename.strip()):
            continue
        if id(f) in seen_ids:
            continue
        seen_ids.add(id(f))
        dedup.append(f)
    files_list = dedup

    # --- Fallback: se não veio form-data válido, tenta JSON {"text": "..."} ---
    if (not files_list) and (not (text and str(text).strip())):
        try:
            if "application/json" in (request.headers.get("content-type") or ""):
                body = await request.json()
                text = (body.get("text") or "").strip()
        except Exception:
            pass

    # --- Regra de exclusividade: texto OU arquivo(s), nunca ambos ---
    has_text = bool(text and str(text).strip())
    has_files = bool(files_list)

    if has_text and has_files:
        raise HTTPException(
            status_code=400,
            detail="Escolha apenas UM modo de entrada: texto OU arquivo(s).",
        )

    # --- Caso: Texto ---
    if has_text:
        label, conf, suggestion = decide_and_suggest(text)
        results.append({
            "source": "input_text",
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })

    # --- Caso: Arquivos ---
    if has_files:
        for f in files_list:
            raw = await f.read()
            # ignora anexos vazios (sem bytes)
            if not raw:
                continue

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
            results.append({
                "source": filename,
                "category": label,
                "confidence": conf,
                "suggestion": suggestion
            })

    # Nada enviado
    if not results:
        raise HTTPException(
            status_code=400,
            detail="Envie APENAS 'text' (JSON ou form-data) OU APENAS 'file(s)' como multipart/form-data.",
        )

    return results
