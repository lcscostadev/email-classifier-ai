def hf_generate_reply(category: str, email_text: str) -> str:
    """
    Gera uma resposta curta e educada em PT-BR com FLAN-T5 (text2text).
    """
    url = "https://api-inference.huggingface.co/models/google/flan-t5-base"
    prompt = (
        "Você é um assistente de suporte ao cliente de uma empresa financeira.\n"
        f"Categoria do email: {category}\n"
        "Objetivo: redigir uma resposta breve, educada e clara em português do Brasil.\n"
        "Se for Produtivo: confirme recebimento, explique próximo passo e prazo curto.\n"
        "Se for Improdutivo: agradeça e informe que não é necessária ação.\n\n"
        f"Email do cliente:\n\"{email_text}\"\n\n"
        "Resposta:"
    )
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 120, "temperature": 0.2}
    }
    r = httpx.post(url, headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    # Em text2text, geralmente vem como [{"generated_text": "..."}]
    try:
        return data[0]["generated_text"].strip()
    except Exception:
        # fallback simples
        return "Olá! Obrigado pela mensagem. Em breve retornaremos com mais informações."
