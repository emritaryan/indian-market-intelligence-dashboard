import React, { useEffect, useRef, useState } from 'react';

const defaults = { short_sma: 6, long_sma: 30, lookback_days: 730, max_stocks: 100 };
const fields = [
  ['short_sma', 'Short SMA', 1, 249, 'Trading sessions'],
  ['long_sma', 'Long SMA', 2, 250, 'Trading sessions'],
  ['lookback_days', 'Lookback Days', 1, 3650, 'Calendar days to scan'],
  ['max_stocks', 'Max Stocks', 1, 100, 'Alphabetical selection'],
];
const number = value => value == null ? '—' : Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Signals({ onSessionExpired }) {
  const [form, setForm] = useState(defaults);
  const [job, setJob] = useState({ status: 'idle' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const expire = useRef(onSessionExpired);
  expire.current = onSessionExpired;
  const mounted = useRef(true);
  async function request(options) {
    const response = await fetch('/api/signals', { ...options, headers: { 'Content-Type': 'application/json' }, cache: 'no-store' });
    if (response.status === 401) { expire.current(); throw new Error('Please sign in again.'); }
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the scanner inputs and try again.');
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
      } catch (e) { if (mounted.current) setError(e.message || 'Could not reach the backend.'); }
      // Polling also restores in-progress scans after switching tabs or refreshing.
      if (mounted.current) timer = setTimeout(poll, 2000);
    }
    poll();
    return () => { mounted.current = false; clearTimeout(timer); };
  }, []);

  async function generate(event) {
    event.preventDefault();
    const settings = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, Number(value)]));
    if (settings.short_sma >= settings.long_sma) { setError('Short SMA must be smaller than Long SMA.'); return; }
    setError(''); setSubmitting(true);
    try {
      const data = await request({ method: 'POST', body: JSON.stringify(settings) });
      if (mounted.current) setJob(data);
    } catch (e) { if (mounted.current) setError(e.message || 'Could not start the scan.'); }
    finally { if (mounted.current) setSubmitting(false); }
  }
  const running = submitting || job.status === 'running';
  const result = job.result;
  const rows = result?.rows || [];
  const settings = result?.settings || defaults;
  const bullish = rows.filter(row => row.crossover_type === 'Bullish').length;
  const bearish = rows.filter(row => row.crossover_type === 'Bearish').length;
  const progress = job.total ? Math.round(job.completed / job.total * 100) : 0;
  return <section className="signals">
    <div className="section-title"><div><p className="eyebrow">NIFTY 100 · TREND RESEARCH</p><h2>SMA crossover scanner</h2><p className="muted">Find the latest change in direction across India's largest companies.</p></div><span className="outline-pill">DAILY CANDLES</span></div>
    <form className="card scan-form" onSubmit={generate}>
      <div className="scan-inputs">{fields.map(([key, label, min, max, hint]) => <label key={key}>{label}<input type="number" min={min} max={max} step="1" required disabled={running} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}/><span className="hint">{hint}</span></label>)}</div>
      <div className="scan-actions"><p className="muted">Completed sessions only. Most recent crossover per stock.</p><button className="primary" disabled={running}>{running ? 'Scanning…' : 'Generate Signals →'}</button></div>
    </form>
    {error && <div role="alert" className="error">{error}</div>}
    {job.status === 'error' && <div role="alert" className="error">{job.message}</div>}
    {running && <div className="scan-progress" role="status"><div><span>{job.message || 'Starting scan…'}</span><span>{job.completed || 0} / {job.total || form.max_stocks} stocks</span></div><progress max="100" value={progress}/><p className="hint">A full scan can take a few minutes. You can switch tabs while it runs. Backend restarts interrupt active scans.</p></div>}
    {result && <>
      <div className="signal-summary"><article><span className="eyebrow">STOCKS SCANNED</span><strong>{rows.length}</strong></article><article><span className="eyebrow">LATEST BULLISH</span><strong className="positive">{bullish}</strong></article><article><span className="eyebrow">LATEST BEARISH</span><strong className="negative">{bearish}</strong></article><article><span className="eyebrow">OTHER / NO CROSSOVER</span><strong>{rows.length - bullish - bearish}</strong></article></div>
      <div className="results-heading"><div><h2>Crossover signals</h2><p className="muted">{result.from_date} — {result.to_date} · Ranked newest first</p></div><span className="count">SMA {settings.short_sma} / {settings.long_sma}</span></div>
      {result.warnings.length > 0 && <details className="scan-warning"><summary>{result.warnings.length} stock(s) need attention</summary><ul>{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>}
      <div className="table-wrap"><table><caption className="sr-only">Nifty 100 latest SMA crossover signals</caption><thead><tr><th>Rank</th><th>Ticker</th><th>Company</th><th>Crossover Type</th><th>Crossover Date</th><th className="numeric">Close</th><th className="numeric">SMA {settings.short_sma}</th><th className="numeric">SMA {settings.long_sma}</th></tr></thead><tbody>{rows.map(row => <tr key={row.ticker}><td className="rank">{String(row.rank).padStart(2, '0')}</td><td className="ticker">{row.ticker}</td><td className="company">{row.company}</td><td><span className={`signal-badge ${row.crossover_type.toLowerCase()}`}>{row.crossover_type === 'Bullish' ? '↗ ' : row.crossover_type === 'Bearish' ? '↘ ' : ''}{row.crossover_type}</span></td><td className="date">{row.crossover_date || '—'}</td><td className="numeric">{number(row.close)}</td><td className="numeric">{number(row.short_sma)}</td><td className="numeric">{number(row.long_sma)}</td></tr>)}</tbody></table></div>
      <p className="hint table-note">Close and SMA values are from the crossover date. Stocks without a crossover are listed last. Current Nifty 100 membership is used. Generated {new Date(result.generated_at).toLocaleString()}.</p>
    </>}
    {!result && !running && job.status !== 'error' && <div className="signals-empty"><span className="empty-symbol">↗</span><h2>Your next signal starts here</h2><p className="muted">Choose your SMA periods and generate a scan.<br/>Bullish and bearish crossovers will appear here, newest first.</p><span className="hint">Official Nifty Indices constituents · Zerodha historical data</span></div>}
  </section>;
}
