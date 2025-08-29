# import os
# import re
# from io import BytesIO
# from typing import List, Optional, Union

# import httpx
# from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import HTMLResponse
# from pdfminer.high_level import extract_text as pdf_extract

# # Local ML (fallback)
# from nlp import classify as local_classify
# from templates import PRODUCTIVE_REPLY, NON_PRODUCTIVE_REPLY

# # --------- Config HF (opcional) ----------
# USE_HF_ENV = os.getenv("USE_HF") == "1"
# HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
# USE_HF = bool(USE_HF_ENV and HF_TOKEN)  # só ativa HF se houver token

# HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
# HF_ZERO_SHOT_MODEL = "facebook/bart-large-mnli"
# HF_T2T_MODEL = "google/flan-t5-base"  # para gerar resposta curta em PT-BR

# # --------- Regras de negócio (saudações/boas festas) ----------
# HOLIDAY_PATTERNS = [
#     r"\bfeliz\s+natal\b",
#     r"\bboas\s+festas\b",
#     r"\bfeliz\s+ano\s+novo\b",
#     r"\bbo[mn]\s+natal\b",
#     r"\bmerry\s+christmas\b",
#     r"\bhappy\s+new\s+year\b",
# ]

# def is_holiday_greeting(text: str) -> bool:
#     t = (text or "").lower()
#     t = re.sub(r"\s+", " ", t)
#     return any(re.search(p, t, flags=re.IGNORECASE) for p in HOLIDAY_PATTERNS)


# def hf_zero_shot_productive(text: str):
#     """Zero-shot (BART-MNLI) com fallback local."""
#     url = f"https://api-inference.huggingface.co/models/{HF_ZERO_SHOT_MODEL}"
#     payload = {
#         "inputs": text,
#         "parameters": {"candidate_labels": ["Produtivo", "Improdutivo"], "multi_label": False},
#     }
#     try:
#         r = httpx.post(url, headers=HF_HEADERS, json=payload, timeout=45)
#         r.raise_for_status()
#         data = r.json()
#         label = data["labels"][0]
#         score = float(data["scores"][0])
#         return label, score
#     except Exception as e:
#         print(f"[HF zero-shot] erro: {e}", flush=True)
#         return local_classify(text)


# def hf_generate_reply(category: str, email_text: str) -> str:
#     """Gera resposta breve em PT-BR (FLAN-T5) com fallback."""
#     url = f"https://api-inference.huggingface.co/models/{HF_T2T_MODEL}"
#     prompt = (
#         "Você é um assistente de suporte ao cliente de uma empresa financeira.\n"
#         f"Categoria do email: {category}\n"
#         "Objetivo: redigir uma resposta breve, educada e clara em português do Brasil.\n"
#         "- Se for Produtivo: confirme recebimento, explique próximo passo e prazo curto.\n"
#         "- Se for Improdutivo: agradeça e informe que não é necessária ação.\n\n"
#         f"Email do cliente:\n\"{email_text}\"\n\n"
#         "Resposta:"
#     )
#     try:
#         r = httpx.post(
#             url,
#             headers=HF_HEADERS,
#             json={"inputs": prompt, "parameters": {"max_new_tokens": 120, "temperature": 0.2}},
#             timeout=60,
#         )
#         r.raise_for_status()
#         data = r.json()
#         text = (data[0].get("generated_text") or "").strip()
#         if text:
#             return text
#     except Exception as e:
#         print(f"[HF generate] erro: {e}", flush=True)

#     return PRODUCTIVE_REPLY if category == "Produtivo" else NON_PRODUCTIVE_REPLY


# def decide_and_suggest(text: str):
#     """
#     Curto-circuito para saudações; depois HF (se ativo) ou classificador local.
#     """
#     if is_holiday_greeting(text):
#         return "Improdutivo", 0.95, NON_PRODUCTIVE_REPLY

#     if USE_HF:
#         label, conf = hf_zero_shot_productive(text)
#         suggestion = hf_generate_reply(label, text)
#         return label, conf, suggestion

#     label, conf = local_classify(text)
#     suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY
#     return label, conf, suggestion


# # --------- FastAPI App ----------
# app = FastAPI(title="Email Classifier API", openapi_version="3.0.2")

# # CORS (ajuste allow_origins para seu domínio do front em produção)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# def read_txt_bytes(b: bytes) -> str:
#     try:
#         return b.decode("utf-8", errors="ignore")
#     except Exception:
#         return b.decode("latin-1", errors="ignore")


# @app.get("/", response_class=HTMLResponse)
# def root():
#     mode = "HF" if USE_HF else "LOCAL"
#     return f"""
#     <html>
#       <head><title>Email Classifier API</title></head>
#       <body style="font-family: sans-serif; max-width: 720px; margin: 40px auto;">
#         <h1>Email Classifier API</h1>
#         <p>API online ✅ — Modo: <strong>{mode}</strong></p>
#         <ul>
#           <li><a href="/api/health">/api/health</a></li>
#           <li><a href="/docs">/docs</a> (Swagger)</li>
#         </ul>
#       </body>
#     </html>
#     """


# @app.get("/api/health")
# def health():
#     return {"status": "ok", "mode": "HF" if USE_HF else "LOCAL"}


# @app.post("/api/process")
# async def process_emails(
#     request: Request,
#     # aceita 1 OU vários no mesmo campo 'files'
#     files: Optional[Union[UploadFile, List[UploadFile]]] = File(default=None),
#     text: Optional[str] = Form(default=None),
# ):
#     results: List[dict] = []

#     # --- normaliza 'files' para uma lista única ---
#     files_list: List[UploadFile] = []
#     if isinstance(files, UploadFile):
#         files_list = [files]
#     elif isinstance(files, list) and files:
#         files_list = files
#     else:
#         # tenta capturar 'files' ou 'files[]' que alguns clientes mandam
#         try:
#             form = await request.form()
#             alt_list = form.getlist("files") or form.getlist("files[]")
#             files_list = [f for f in alt_list if isinstance(f, UploadFile)]
#         except Exception:
#             pass

#     # --- fallback JSON {"text": "..."} se não veio form-data válido ---
#     if (not files_list) and (not (text and str(text).strip())):
#         try:
#             if "application/json" in (request.headers.get("content-type") or ""):
#                 body = await request.json()
#                 text = (body.get("text") or "").strip()
#         except Exception:
#             pass

#     # --- Exclusividade: texto OU arquivo(s) ---
#     has_text = bool(text and str(text).strip())
#     has_files = bool(files_list)

#     if has_text and has_files:
#         raise HTTPException(
#             status_code=400,
#             detail="Escolha apenas UM modo de entrada: texto OU arquivo(s).",
#         )

#     # --- Texto ---
#     if has_text:
#         label, conf, suggestion = decide_and_suggest(text)  # type: ignore[arg-type]
#         results.append({
#             "source": "input_text",
#             "category": label,
#             "confidence": conf,
#             "suggestion": suggestion
#         })

#     # --- Arquivos ---
#     if has_files:
#         dedup: List[UploadFile] = []
#         seen_ids = set()
#         for f in files_list:
#             if not isinstance(f, UploadFile):
#                 continue
#             if not (f.filename and f.filename.strip()):
#                 continue
#             if id(f) in seen_ids:
#                 continue
#             seen_ids.add(id(f))
#             dedup.append(f)
#         files_list = dedup

#         for f in files_list:
#             raw = await f.read()
#             if not raw:
#                 continue

#             filename = f.filename or "file"

#             if filename.lower().endswith(".pdf") or (f.content_type or "").lower() == "application/pdf":
#                 try:
#                     content = pdf_extract(BytesIO(raw))
#                     if not content or not content.strip():
#                         raise ValueError("PDF sem texto extraível (possivelmente digitalizado ou protegido).")
#                 except Exception as e:
#                     raise HTTPException(
#                         status_code=400,
#                         detail=f"Falha ao ler PDF '{filename}': {e}",
#                     )
#             else:
#                 content = read_txt_bytes(raw)

#             label, conf, suggestion = decide_and_suggest(content)
#             results.append({
#                 "source": filename,
#                 "category": label,
#                 "confidence": conf,
#                 "suggestion": suggestion
#             })

#     if not results:
#         raise HTTPException(
#             status_code=400,
#             detail="Envie APENAS 'text' (JSON ou form-data) OU APENAS 'files' como multipart/form-data.",
#         )

#     return results

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
    r"\bbo[mn]\s+natal\b",
    r"\bmerry\s+christmas\b",
    r"\bhappy\s+new\s+year\b",
]

def is_holiday_greeting(text: str) -> bool:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t)
    return any(re.search(p, t, flags=re.IGNORECASE) for p in HOLIDAY_PATTERNS)


def hf_zero_shot_productive(text: str):
    """Zero-shot (BART-MNLI) com fallback local."""
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
        return local_classify(text)


def hf_generate_reply(category: str, email_text: str) -> str:
    """Gera resposta breve em PT-BR (FLAN-T5) com fallback."""
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
    Curto-circuito para saudações; depois HF (se ativo) ou classificador local.
    """
    if is_holiday_greeting(text):
        return "Improdutivo", 0.95, NON_PRODUCTIVE_REPLY

    if USE_HF:
        label, conf = hf_zero_shot_productive(text)
        suggestion = hf_generate_reply(label, text)
        return label, conf, suggestion

    label, conf = local_classify(text)
    suggestion = PRODUCTIVE_REPLY if label == "Produtivo" else NON_PRODUCTIVE_REPLY
    return label, conf, suggestion


# --------- FastAPI App ----------
app = FastAPI(title="Email Classifier API", openapi_version="3.0.2")

# CORS (ajuste allow_origins para seu domínio do front em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    files: Union[UploadFile, List[UploadFile], None] = File(default=None),
    text: Optional[str] = Form(default=None),
):
    results: List[dict] = []

    # Debug logs
    print(f"[DEBUG] text recebido: {bool(text and text.strip())}")
    print(f"[DEBUG] files recebido: {files}")
    print(f"[DEBUG] tipo de files: {type(files)}")

    # --- Processamento de texto ---
    if text and text.strip():
        print("[DEBUG] Processando texto...")
        label, conf, suggestion = decide_and_suggest(text.strip())
        results.append({
            "source": "input_text",
            "category": label,
            "confidence": conf,
            "suggestion": suggestion
        })
        return results

    # --- Processamento de arquivos ---
    files_list = []
    
    # Tenta múltiplas abordagens para capturar arquivos
    if files:
        print(f"[DEBUG] files não é None, tipo: {type(files)}")
        if isinstance(files, UploadFile):
            files_list = [files]
            print(f"[DEBUG] Arquivo único: {files.filename}")
        elif isinstance(files, list):
            files_list = files
            print(f"[DEBUG] Lista de arquivos: {[f.filename if f else 'None' for f in files]}")
    
    # Se não funcionou pela forma padrão, tenta pelo form manual
    if not files_list:
        print("[DEBUG] Tentando capturar arquivos via form...")
        try:
            form = await request.form()
            print(f"[DEBUG] Form keys: {list(form.keys())}")
            
            # Tenta diferentes variações do nome do campo
            for field_name in ['files', 'files[]', 'file']:
                if field_name in form:
                    field_value = form.getlist(field_name) if hasattr(form, 'getlist') else [form[field_name]]
                    for item in field_value:
                        if isinstance(item, UploadFile):
                            files_list.append(item)
                            print(f"[DEBUG] Arquivo encontrado via {field_name}: {item.filename}")
        except Exception as e:
            print(f"[DEBUG] Erro ao processar form: {e}")
    
    if files_list:
        print(f"[DEBUG] Total de arquivos para processar: {len(files_list)}")
        
        # Filtra arquivos válidos
        valid_files = []
        for f in files_list:
            if f and hasattr(f, 'filename') and f.filename and f.filename.strip():
                valid_files.append(f)
                print(f"[DEBUG] Arquivo válido: {f.filename}")
            else:
                print(f"[DEBUG] Arquivo inválido: {f}")
@app.post("/api/process")
async def process_emails(request: Request):
    results: List[dict] = []

    try:
        # Captura o form completo manualmente
        form = await request.form()
        print(f"[DEBUG] Form keys disponíveis: {list(form.keys())}")
        print(f"[DEBUG] Content-Type: {request.headers.get('content-type')}")

        # Verifica se há texto
        text_value = None
        for key in ['text', 'emailText']:
            if key in form:
                text_value = form[key]
                break
        
        if text_value and str(text_value).strip():
            print(f"[DEBUG] Processando texto de campo '{key}'")
            label, conf, suggestion = decide_and_suggest(str(text_value).strip())
            results.append({
                "source": "input_text",
                "category": label,
                "confidence": conf,
                "suggestion": suggestion
            })
            return results

        # Verifica se há arquivos em qualquer campo possível
        file_fields = ['files', 'file', 'emailFiles', 'upload', 'documents']
        files_found = []
        
        for field_name in file_fields:
            if field_name in form:
                print(f"[DEBUG] Campo '{field_name}' encontrado")
                field_value = form[field_name]
                
                if isinstance(field_value, UploadFile):
                    files_found.append(field_value)
                    print(f"[DEBUG] Arquivo único em '{field_name}': {field_value.filename}")
                elif hasattr(form, 'getlist'):
                    # FastAPI form pode ter getlist para múltiplos valores
                    try:
                        multiple_files = form.getlist(field_name)
                        for item in multiple_files:
                            if isinstance(item, UploadFile):
                                files_found.append(item)
                                print(f"[DEBUG] Arquivo múltiplo em '{field_name}': {item.filename}")
                    except Exception as e:
                        print(f"[DEBUG] Erro ao buscar múltiplos em '{field_name}': {e}")

        print(f"[DEBUG] Total de arquivos encontrados: {len(files_found)}")
        
        if files_found:
            # Processa os arquivos encontrados
            for file in files_found:
                try:
                    print(f"[DEBUG] Processando arquivo: {file.filename}")
                    
                    # Lê o conteúdo do arquivo
                    file_content = await file.read()
                    print(f"[DEBUG] Tamanho do arquivo: {len(file_content)} bytes")
                    
                    if not file_content:
                        results.append({
                            "source": file.filename,
                            "error": "Arquivo vazio",
                            "category": None,
                            "confidence": 0,
                            "suggestion": None
                        })
                        continue

                    filename = file.filename.lower()
                    content_type = (file.content_type or "").lower()
                    print(f"[DEBUG] Content-type: {content_type}")

                    # Extração de texto baseada no tipo de arquivo
                    if filename.endswith(".pdf") or content_type == "application/pdf":
                        try:
                            print("[DEBUG] Extraindo texto do PDF...")
                            content = pdf_extract(BytesIO(file_content))
                            if not content or not content.strip():
                                raise ValueError("PDF sem texto extraível")
                            print(f"[DEBUG] Texto extraído: {len(content)} caracteres")
                        except Exception as e:
                            print(f"[DEBUG] Erro PDF: {e}")
                            results.append({
                                "source": file.filename,
                                "error": f"Erro ao processar PDF: {str(e)}",
                                "category": None,
                                "confidence": 0,
                                "suggestion": None
                            })
                            continue
                    else:
                        # Arquivo de texto
                        print("[DEBUG] Processando como texto...")
                        content = read_txt_bytes(file_content)

                    # Verifica se há conteúdo para classificar
                    if not content or not content.strip():
                        results.append({
                            "source": file.filename,
                            "error": "Arquivo sem conteúdo de texto",
                            "category": None,
                            "confidence": 0,
                            "suggestion": None
                        })
                        continue

                    print(f"[DEBUG] Classificando texto de {len(content)} chars...")
                    # Classifica o conteúdo
                    label, conf, suggestion = decide_and_suggest(content.strip())
                    results.append({
                        "source": file.filename,
                        "category": label,
                        "confidence": conf,
                        "suggestion": suggestion
                    })
                    print(f"[DEBUG] Resultado: {label} ({conf})")

                except Exception as e:
                    print(f"[DEBUG] Erro geral ao processar {file.filename}: {e}")
                    results.append({
                        "source": file.filename,
                        "error": f"Erro interno: {str(e)}",
                        "category": None,
                        "confidence": 0,
                        "suggestion": None
                    })

            return results

    except Exception as e:
        print(f"[DEBUG] Erro ao processar form: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao processar requisição: {str(e)}"
        )

    # Se chegou até aqui, não há texto nem arquivos
    raise HTTPException(
        status_code=400,
        detail="Nenhum conteúdo encontrado. Envie texto ou arquivos válidos."
    )