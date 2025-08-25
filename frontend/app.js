const form = document.getElementById('emailForm')
const fileInput = document.getElementById('emailFiles')
const textInput = document.getElementById('emailText')
const resultsDiv = document.getElementById('results')

const API_URL = "http://localhost:8000/api/process"

form.addEventListener("submit", async e => {
  e.preventDefault()
  resultsDiv.innerHTML = "Processing..."

  try{
    const formData = new FormData()

    if(fileInput.files?.length) {
      for(const f of fileInput.files) {
        formData.append("files", f)
      }
    }

    if(textInput.value.trim()) {
      formData.append("text", textInput.value.trim())
    }

    if(!fileInput.files.length && !textInput.value.trim()) {
      resultsDiv.innerHTML = "<p>Oops, you forgot paste any text or send a file</p>"
      return
    }

    const res = await fetch(API_URL, {method: "POST", body: formData})
    if(!res.ok) throw new Error("Error while processing...")

    const data = await res.json()
    // ainda não sei como os dados vão ser mostrados
  } catch(err) {
    console.error(err)
    resultsDiv.innerHTML = "<p>File processing has failed, try again.</p>"
  }
})