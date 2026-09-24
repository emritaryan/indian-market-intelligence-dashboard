import React, { useEffect, useRef, useState } from 'react';

const defaults = { max_recommendations: 50 };
const rules = [
  { label: 'RSI', parameter: '14-day RSI', threshold: '> 60', note: 'Confirms strong positive momentum' },
  { label: 'MACD', parameter: '12 · 26 · 9', threshold: 'Line > Signal', note: 'Confirms momentum is accelerating' },
  { label: 'EMA 50', parameter: 'Closing price', threshold: 'Close > EMA 50', note: 'Confirms the medium-term uptrend' },
  { label: 'EMA 200', parameter: 'Closing price', threshold: 'Close > EMA 200', note: 'Confirms the long-term uptrend' },
];
const number = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString('en-IN', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
});

export default function MomentumIndicator({ onSessionExpired }) {
  const [form, setForm] = useState(defaults);
  const [job, setJob] = useState({ status: 'idle' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const expire = useRef(onSessionExpired);
  const mounted = useRef(true);
  expire.current = onSessionExpired;

  async function request(options) {
    const response = await fetch('/api/momentum', {
      ...options,
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    });
    if (response.status === 401) {
      expire.current();
      throw new Error('Please sign in again.');
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not run the momentum scan.');
    }
    return data;
  }

  useEffect(() => {
    mounted.current = true;
    let timer;
    async function poll() {
      try {
        const data = await request();
        if (!mounted.current) return;
        setJob(data);
        if (data.auth_expired) expire.current();
      } catch (requestError) {
        if (mounted.current) setError(requestError.message || 'Could not reach the backend.');
      }
      if (mounted.current) timer = setTimeout(poll, 2000);
    }
    poll();
    return () => {
      mounted.current = false;
      clearTimeout(timer);
    };
  }, []);

  async function generate(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const data = await request({
        method: 'POST',
        body: JSON.stringify({ max_recommendations: Number(form.max_recommendations) }),
      });
      if (mounted.current) setJob(data);
    } catch (requestError) {
      if (mounted.current) setError(requestError.message || 'Could not start the momentum scan.');
    } finally {
      if (mounted.current) setSubmitting(false);
    }
  }

  const running = submitting || job.status === 'running';
  const progress = job.total ? Math.round((job.completed || 0) / job.total * 100) : 0;
  const result = job.result;
  const rows = result?.rows || [];
  const warnings = result?.warnings || [];

  return <section className="signals momentum-indicator">
    <div className="section-title">
      <div>
        <p className="eyebrow">NIFTY 100 · BULLISH TREND FILTER</p>
        <h2>Momentum indicator</h2>
        <p className="muted">Find stocks where momentum and both medium- and long-term trends agree.</p>
      </div>
      <span className="outline-pill">COMPLETED DAILY CANDLES</span>
    </div>

    <div className="momentum-rules" aria-label="Momentum filter parameters">
      {rules.map(rule => <article className="momentum-rule" key={rule.label}>
        <span className="eyebrow">{rule.label}</span>
        <strong>{rule.threshold}</strong>
        <p>{rule.parameter}</p>
        <small>{rule.note}</small>
      </article>)}
    </div>

    <form className="card momentum-controls" onSubmit={generate}>
      <label>Maximum recommendations
        <input type="number" min="1" max="50" step="1" required disabled={running}
          value={form.max_recommendations}
          onChange={event => setForm({ max_recommendations: event.target.value })}/>
        <span className="hint">Up to 50 qualifying Nifty 100 stocks</span>
      </label>
      <div>
        <p className="muted">All four conditions must pass on the latest completed trading session.</p>
        <button className="primary" disabled={running}>{running ? 'Scanning…' : 'Find Bullish Stocks →'}</button>
      </div>
    </form>

    {error && <div role="alert" className="error">{error}</div>}
    {job.status === 'error' && <div role="alert" className="error">{job.message}</div>}
    {running && <div className="scan-progress" role="status">
      <div><span>{job.message || 'Starting scan…'}</span><span>{job.completed || 0} / {job.total || 100} stocks</span></div>
      <progress max="100" value={progress}/>
      <p className="hint">The scan checks the full Nifty 100 and can take a few minutes. You may switch tabs while it runs.</p>
    </div>}

    {result && <>
      <div className="signal-summary momentum-summary">
        <article><span className="eyebrow">UNIVERSE SCANNED</span><strong>{result.universe_size}</strong></article>
        <article><span className="eyebrow">BULLISH MATCHES</span><strong className="positive">{result.matched_total}</strong></article>
        <article><span className="eyebrow">RESULTS SHOWN</span><strong>{rows.length}</strong></article>
        <article><span className="eyebrow">AS OF SESSION</span><strong className="momentum-date">{result.as_of}</strong></article>
      </div>
      <div className="results-heading">
        <div><h2>Bullish momentum candidates</h2><p className="muted">All four rules passed · {result.ranking}</p></div>
        <span className="count">MAX {result.settings.max_recommendations}</span>
      </div>
      {warnings.length > 0 && <details className="scan-warning"><summary>{warnings.length} stock(s) need attention</summary><ul>{warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>}
      {rows.length > 0 ? <div className="table-wrap momentum-table"><table>
        <caption className="sr-only">Nifty 100 stocks passing the bullish momentum filter</caption>
        <thead><tr><th>Rank</th><th>Ticker</th><th>Company</th><th>Session</th><th className="numeric">Close</th><th className="numeric">RSI 14</th><th className="numeric">MACD</th><th className="numeric">Signal</th><th className="numeric">EMA 50</th><th className="numeric">EMA 200</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.ticker}>
          <td className="rank">{String(row.rank).padStart(2, '0')}</td>
          <td className="ticker">{row.ticker}</td>
          <td className="company">{row.company}</td>
          <td className="date">{row.as_of}</td>
          <td className="numeric">{number(row.close)}</td>
          <td className="numeric positive">{number(row.rsi14)}</td>
          <td className="numeric">{number(row.macd_line)}</td>
          <td className="numeric">{number(row.signal_line)}</td>
          <td className="numeric">{number(row.ema50)}</td>
          <td className="numeric">{number(row.ema200)}</td>
        </tr>)}</tbody>
      </table></div> : <div className="signals-empty compact"><span className="empty-symbol">↗</span><h2>No stocks passed all four rules</h2><p className="muted">The filter found no qualifying Nifty 100 stocks for the latest completed session.</p></div>}
      <p className="hint table-note">Technical indicators use Zerodha Kite daily candles. Current Nifty 100 membership comes from the official Nifty Indices constituent file. Generated {new Date(result.generated_at).toLocaleString()}.</p>
    </>}

    {!result && !running && job.status !== 'error' && <div className="signals-empty compact">
      <span className="empty-symbol">↗</span><h2>Scan for bullish alignment</h2>
      <p className="muted">Run the filter to find stocks that pass every displayed momentum rule.</p>
      <span className="hint">Research candidates only · not investment advice</span>
    </div>}
  </section>;
}

