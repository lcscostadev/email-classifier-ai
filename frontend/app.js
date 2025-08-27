const form = document.getElementById('emailForm');
const fileInput = document.getElementById('emailFiles');
const textInput = document.getElementById('emailText');
const resultsDiv = document.getElementById('results');

const API_URL = 'https://email-classifier-ai-oc17.onrender.com/api/process';

// --- UX: manter exclusivo (se digitar, limpa arquivos; se anexar, limpa texto)
textInput.addEventListener('input', () => {
  if (textInput.value.trim().length > 0) {
    // limpa arquivos quando usuário optar por texto
    fileInput.value = '';
  }
});
fileInput.addEventListener('change', () => {
  if (fileInput.files && fileInput.files.length > 0) {
    // limpa texto quando usuário optar por arquivos
    textInput.value = '';
  }
});

function renderResults(items) {
  if (!Array.isArray(items) || !items.length) {
    resultsDiv.innerHTML = '<p>Nenhum resultado retornado.</p>';
    return;
  }

  resultsDiv.innerHTML = items.map(item => `
    <div class="card">
      <div class="card-header">
        <strong>Fonte:</strong> ${item.source ?? '—'}
      </div>
      <div class="card-body">
        <p><strong>Categoria:</strong> ${item.category ?? '—'} (${item.confidence != null ? Math.round(item.confidence * 100) : '—'}%)</p>
        <p><strong>Resposta sugerida:</strong></p>
        <pre class="suggestion" style="white-space:pre-wrap">${item.suggestion ?? '—'}</pre>
        <button class="copy-btn" data-text="${(item.suggestion ?? '').replace(/"/g, '&quot;')}">Copiar resposta</button>
      </div>
    </div>
  `).join('');

  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const txt = btn.getAttribute('data-text') || '';
      try {
        await navigator.clipboard.writeText(txt);
        btn.textContent = 'Copiado!';
        setTimeout(() => (btn.textContent = 'Copiar resposta'), 1200);
      } catch {
        alert('Não foi possível copiar. Copie manualmente.');
      }
    });
  });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const txt = (textInput?.value || '').trim();
  const hasFiles = !!(fileInput.files && fileInput.files.length > 0);
  const hasText = txt.length > 0;

  // Exclusivo: OU texto OU arquivos
  if ((hasText && hasFiles) || (!hasText && !hasFiles)) {
    resultsDiv.innerHTML = '<p>Escolha apenas um modo de entrada: cole um texto <b>ou</b> selecione arquivo(s).</p>';
    return;
  }

  resultsDiv.textContent = 'Processando…';

  const formData = new FormData();
  if (hasFiles) {
    for (const f of fileInput.files) {
      // ignora arquivos “vazios” ou sem nome
      if (f && f.name) formData.append('files', f);
    }
  } else {
    formData.append('text', txt);
  }

  try {
    const res = await fetch(API_URL, { method: 'POST', body: formData });
    if (!res.ok) {
      const errBody = await res.text().catch(() => '');
      console.error('Erro HTTP', res.status, errBody);
      resultsDiv.innerHTML = `
        <p>Falha ao processar (HTTP ${res.status}).</p>
        <pre style="white-space:pre-wrap">${errBody}</pre>
      `;
      return;
    }

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    console.error(err);
    resultsDiv.innerHTML = '<p>Falha ao processar. Tente novamente.</p>';
  }
});
