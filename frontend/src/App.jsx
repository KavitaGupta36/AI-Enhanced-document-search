import { useState } from 'react'
import './App.css'

const sampleQueries = [
  'How do I return a damaged product?',
  'What is the policy for remote work?',
  'How do I request software access?',
]

function App() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('Ready to search the document library.')
  const [error, setError] = useState('')
  const [fileName, setFileName] = useState('')

  async function runSearch(event) {
    event.preventDefault()
    const trimmedQuery = query.trim()

    if (!trimmedQuery) {
      setError('Please enter a question before searching.')
      return
    }

    setLoading(true)
    setError('')
    setStatus('Searching the indexed documents...')

    try {
      const response = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmedQuery, top_k: 5 }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Unable to complete the search.')
      }

      const data = await response.json()
      setAnswer(data.answer || 'No answer returned.')
      setSources(data.sources || [])
      setStatus(`Retrieved ${data.sources?.length || 0} relevant result(s).`)
    } catch (caughtError) {
      setError(caughtError.message)
      setStatus('Search failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(event) {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) {
      return
    }

    const formData = new FormData()
    formData.append('file', selectedFile)

    setLoading(true)
    setError('')
    setStatus(`Uploading ${selectedFile.name}...`)
    setFileName(selectedFile.name)

    try {
      const response = await fetch('http://localhost:8000/api/upload', {
        method: 'POST',
        body: formData,
      })

      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.detail || 'Upload failed.')
      }

      setStatus(`${result.filename} was uploaded and indexed successfully.`)
    } catch (caughtError) {
      setError(caughtError.message)
      setStatus('Upload failed.')
    } finally {
      setLoading(false)
      event.target.value = ''
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">UC07</p>
          <h1>AI-Enhanced Document Search</h1>
        </div>
      </header>

      <main className="layout">
        <section className="panel search-panel">
          <h2>Ask a question</h2>
          <form onSubmit={runSearch} className="search-form">
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows="4"
              placeholder="Ask anything about the indexed documents..."
            />
            <div className="actions">
              <button type="submit" disabled={loading}>
                {loading ? 'Searching...' : 'Search documents'}
              </button>
            </div>
          </form>

          {/* <div className="quick-queries">
            {sampleQueries.map((item) => (
              <button key={item} type="button" onClick={() => setQuery(item)}>
                {item}
              </button>
            ))}
          </div> */}

          <div className="upload-box">
            <label htmlFor="document-upload">Upload a document</label>
            <input id="document-upload" type="file" onChange={handleUpload} />
            {fileName ? <small>Last uploaded: {fileName}</small> : null}
          </div>
        </section>

        <section className="panel answer-panel">
          <h2>Answer</h2>
          {answer ? (
            <div className="answer-box">
              <p>{answer}</p>
            </div>
          ) : (
            <p className="placeholder-text">
              Search a question to get a grounded answer based on the available sources.
            </p>
          )}
        </section>
      </main>

      <section className="panel sources-panel">
        <h2>Source documents</h2>
        {sources.length > 0 ? (
          <ul className="source-list">
            {sources.map((source) => (
              <li key={source.id} className="source-item">
                <div className="source-meta">
                  <span className="source-name">{source.source}</span>
                  <span>Match score: {source.score}</span>
                </div>
                <p>{source.snippet || source.source}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="placeholder-text">
            Relevant snippets will appear here after a search.
          </p>
        )}
      </section>

      <div className="status-row">
        <span className="status-badge">Status</span>
        <p>{status}</p>
      </div>

      {error ? <div className="error-box">{error}</div> : null}
    </div>
  )
}

export default App
