const form = document.getElementById('emailForm');
const fileInput = document.getElementById('emailFiles');
const textInput = document.getElementById('emailText');
const resultsDiv = document.getElementById('results');

const API_URL = 'https://email-classifier-ai-oc17.onrender.com/api/process';

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  resultsDiv.innerHTML = 'Processing…';

  try {
    const formData = new FormData();

    if (fileInput.files?.length) {
      for (const f of fileInput.files) formData.append('files', f);
    }

    if (textInput.value.trim()) {
      formData.append('text', textInput.value.trim());
    }

    if (!fileInput.files.length && !textInput.value.trim()) {
      resultsDiv.innerHTML = '<p>Envie um arquivo ou cole um texto.</p>';
      return;
    }

    const res = await fetch(API_URL, { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Erro ao processar');

    const data = await res.json();
    resultsDiv.innerHTML = data.map(item => `
      <div class="card">
        <div class="card-header">
          <strong>Fonte:</strong> ${item.source}
        </div>
        <div class="card-body">
          <p><strong>Categoria:</strong> ${item.category} (${Math.round(item.confidence * 100)}%)</p>
          <p><strong>Resposta sugerida:</strong><br>${item.suggestion}</p>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error(err);
    resultsDiv.innerHTML = '<p>Falha ao processar. Tente novamente.</p>';
  }
});
