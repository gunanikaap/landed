import { useEffect, useState } from 'react'

const EXAMPLES = [
  "What's my response rate, referral vs cold apply?",
  'Which applications went silent for over 2 weeks?',
  'Average salary target by track?',
  'Show me everything still live',
  'Which companies rejected me after a technical interview?',
]

const LOADING_LINES = [
  'reading the schema…',
  'writing SQL…',
  'querying DuckDB…',
  'checking the numbers…',
]

function Table({ result }) {
  const max = 15
  const rows = result.rows.slice(0, max)
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => <td key={j}>{v === null ? '—' : String(v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {result.row_count > max && (
        <div className="tableNote">showing {max} of {result.row_count} rows</div>
      )}
    </div>
  )
}

function Attempt({ sql, result, index, isFinal }) {
  const errored = result && 'error' in result
  return (
    <div className={`attempt ${errored ? 'errored' : ''}`}>
      <div className="attemptHead">
        <span className="attemptTag">attempt {index + 1}</span>
        {errored
          ? <span className="tag tagError">✗ errored — agent retried</span>
          : <span className="tag tagOk">✓ executed{result ? ` · ${result.row_count} rows` : ''}</span>}
      </div>
      <pre className="sql">{sql.trim()}</pre>
      {errored && <div className="sqlError">{result.error}</div>}
      {!errored && result && isFinal && <Table result={result} />}
    </div>
  )
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadLine, setLoadLine] = useState(0)
  const [resp, setResp] = useState(null)
  const [error, setError] = useState(null)
  const [dataBadge, setDataBadge] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((h) => setDataBadge(h.data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!loading) return
    const t = setInterval(
      () => setLoadLine((i) => (i + 1) % LOADING_LINES.length), 1400)
    return () => clearInterval(t)
  }, [loading])

  async function submit(q) {
    const text = (q ?? question).trim()
    if (!text || loading) return
    setQuestion(text)
    setLoading(true)
    setResp(null)
    setError(null)
    try {
      const r = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      if (!r.ok) throw new Error(`API ${r.status}`)
      setResp(await r.json())
    } catch (e) {
      setError(`Couldn't reach the tower — is the API running? (${e.message})`)
    } finally {
      setLoading(false)
    }
  }

  const lastOkIndex = resp
    ? resp.results.reduce((acc, r, i) => ('error' in r ? acc : i), -1)
    : -1

  return (
    <div className="page">
      <header>
        <div className="brandRow">
          <h1 className="brand">landed<span className="plane">🛬</span></h1>
          {dataBadge && <span className="dataBadge">data · {dataBadge}</span>}
        </div>
        <p className="tagline">ask your job-search pipeline anything</p>
        <div className="runway" aria-hidden="true" />
      </header>

      <main>
        <form
          className="askRow"
          onSubmit={(e) => { e.preventDefault(); submit() }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. which referrals are still live?"
            aria-label="Your question"
            autoFocus
          />
          <button type="submit" disabled={loading || !question.trim()}>
            ask
          </button>
        </form>

        <div className="chips">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => submit(ex)}
              disabled={loading}>
              {ex}
            </button>
          ))}
        </div>

        {loading && (
          <div className="loader">
            <div className="strip"><span className="taxi">✈</span></div>
            <div className="loaderText">{LOADING_LINES[loadLine]}</div>
          </div>
        )}

        {error && <div className="errorBox">{error}</div>}

        {resp && !loading && (
          <section className="result">
            <div className="answerCard">
              <div className="status">
                <span className="dot" /> status · landed
              </div>
              <p className="answer">{resp.answer}</p>
            </div>

            {resp.sql.length > 0 && (
              <details className="flightPath" open={resp.sql.length > 1}>
                <summary>
                  flight path · {resp.sql.length}{' '}
                  {resp.sql.length === 1 ? 'query' : 'queries'}
                  {resp.results.some((r) => 'error' in r) && ' · self-corrected'}
                </summary>
                {resp.sql.map((s, i) => (
                  <Attempt key={i} sql={s} result={resp.results[i]}
                    index={i} isFinal={i === lastOkIndex} />
                ))}
              </details>
            )}
          </section>
        )}
      </main>

      <footer>
        <a href="https://github.com/gunanikaap/landed" target="_blank"
          rel="noreferrer">github.com/gunanikaap/landed</a>
        <span className="foot">· DuckDB · FastAPI · React · LLM tool-use</span>
      </footer>
    </div>
  )
}
