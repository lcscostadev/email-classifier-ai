import re
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline

try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords")

PT_STOPWORDS = set(nltk.corpus.stopwords.words('portuguese'))

def clean_text(txt: str) -> str:
    txt = txt.lower()
    txt = re.sub(r'https?://\S+|www\.\S+', ' ', txt)
    txt = re.sub(r'[\d\W_]+', ' ', txt, flags=re.UNICODE)
    tokens = [t for t in txt.split() if t not in PT_STOPWORDS and len(t) > 2]
    return ' '.join(tokens)

X_train = [
    "preciso do status da solicitação 1234 anexo comprovante",
    "poderiam atualizar meu chamado em aberto erro no sistema",
    "segue arquivo para análise por favor confirmar recebimento",
    "bom dia feliz natal para todos",
    "obrigado pela atenção ótimo trabalho",
    "parabéns pelo projeto sucesso a todos",
]
y_train = [
    "Produtivo", "Produtivo", "Produtivo",
    "Improdutivo", "Improdutivo", "Improdutivo"
]

model: Pipeline = Pipeline([
    ('tfidf', TfidfVectorizer(preprocessor=clean_text, ngram_range=(1,2))),
    ('clf', ComplementNB()) 
])

model.fit(X_train, y_train)

def classify(text: str):
    proba = model.predict_proba([text])[0]
    label = model.predict([text])[0]
    # probas na ordem model.classes_
    label2idx = {lbl: i for i, lbl in enumerate(model.classes_)}
    confidence = float(proba[label2idx[label]])
    return label, confidence
