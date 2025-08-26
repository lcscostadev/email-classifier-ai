// const form = document.getElementById('emailForm');
// const fileInput = document.getElementById('emailFiles');
// const textInput = document.getElementById('emailText');
// const resultsDiv = document.getElementById('results');

// const API_URL = 'https://email-classifier-ai-oc17.onrender.com/api/process';

// form.addEventListener('submit', async (e) => {
//   e.preventDefault();
//   resultsDiv.innerHTML = 'Processing…';

//   try {
//     const formData = new FormData();

//     if (fileInput.files?.length) {
//       for (const f of fileInput.files) formData.append('files', f);
//     }

//     if (textInput.value.trim()) {
//       formData.append('text', textInput.value.trim());
//     }

//     if (!fileInput.files.length && !textInput.value.trim()) {
//       resultsDiv.innerHTML = '<p>Envie um arquivo ou cole um texto.</p>';
//       return;
//     }

//     const res = await fetch(API_URL, { method: 'POST', body: formData });
//     if (!res.ok) throw new Error('Erro ao processar');

//     const data = await res.json();
//     resultsDiv.innerHTML = data.map(item => `
//       <div class="card">
//         <div class="card-header">
//           <strong>Fonte:</strong> ${item.source}
//         </div>
//         <div class="card-body">
//           <p><strong>Categoria:</strong> ${item.category} (${Math.round(item.confidence * 100)}%)</p>
//           <p><strong>Resposta sugerida:</strong><br>${item.suggestion}</p>
//         </div>
//       </div>
//     `).join('');
//   } catch (err) {
//     console.error(err);
//     resultsDiv.innerHTML = '<p>Falha ao processar. Tente novamente.</p>';
//   }
// });


const form = document.getElementById('emailForm');
const fileInput = document.getElementById('emailFiles');
const textInput = document.getElementById('emailText'); // <textarea id="emailText">
const resultsDiv = document.getElementById('results');

const API_URL = 'https://email-classifier-ai-oc17.onrender.com/api/process';

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

  // liga os botões "Copiar resposta"
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
  const hasFiles = !!(fileInput.files && fileInput.files.length);

  if (!hasFiles && !txt) {
    resultsDiv.innerHTML = '<p>Envie um arquivo ou cole um texto.</p>';
    return;
  }

  resultsDiv.innerHTML = 'Processando…';

  const formData = new FormData();
  if (hasFiles) {
    for (const f of fileInput.files) formData.append('files', f);
  }
  if (txt) formData.append('text', txt);

  try {
    const res = await fetch(API_URL, { method: 'POST', body: formData });

    // >>> tratamento de erro com status + corpo (como você pediu)
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
