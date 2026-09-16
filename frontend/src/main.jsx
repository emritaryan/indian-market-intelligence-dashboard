import React, { useEffect, useState, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import './expanded.css';
import Signals from './Signals.jsx';
const Overview = lazy(() => import('./Overview.jsx'));
const StockView = lazy(() => import('./StockView.jsx'));

async function api(path, options = {}) {
  const response = await fetch(`/api/${path}`, { ...options, headers: { 'Content-Type': 'application/json' }, cache: 'no-store' });
  let data;
  try { data = await response.json(); } catch { throw new Error('Backend unavailable. Start FastAPI and try again.'); }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Please check the form and try again.');
    error.status = response.status;
    throw error;
  }
  return data;
}

function App() {
  const [profile, setProfile] = useState(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('User');
  const [form, setForm] = useState({ api_key: '', api_secret: '', request_token: '' });
  async function refresh(initial = false) {
    setBusy(true); setError('');
    try { setProfile(await api('profile')); }
    catch (e) { if (e.status === 401) setProfile(null); if (!(initial && e.status === 401)) setError(e.message); }
    finally { setChecking(false); setBusy(false); }
  }
  useEffect(() => { refresh(true); }, []);
  async function login(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const data = await api('login', { method: 'POST', body: JSON.stringify(form) });
      setForm({ api_key: '', api_secret: '', request_token: '' });
      setProfile(data.profile); setTab('User');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError('');
    try { await api('logout', { method: 'POST' }); setProfile(null); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  const brand = <div className="brand"><span className="mark">AK</span><div>Ankit Kumar<small>PERSONAL MARKET WORKSPACE</small></div></div>;
  if (checking) return <main className="loading"><span className="mark">AK</span><p>Checking your saved session…</p></main>;
  if (!profile) return <main className="login-layout"><section className="intro">{brand}<div><p className="eyebrow">YOUR MARKETS. YOUR PERSPECTIVE.</p><h1>A clearer view<br/>starts here.</h1><p className="intro-copy">Connect your Zerodha account to your personal research workspace.</p><div className="visual-lines"><i/><i/><i/><i/><i/><i/><i/><i/><i/></div></div><p className="muted">LOCAL WORKSPACE <span className="dot"/> POWERED BY KITE CONNECT</p></section><section className="login-side"><form onSubmit={login} className="login-card"><span className="eyebrow">ACCOUNT CONNECTION</span><h2>Welcome to Ankit Kumar</h2><p className="muted">Sign in with your Kite Connect credentials.</p><label>API Key<input required autoComplete="off" value={form.api_key} onChange={e => setForm({...form, api_key: e.target.value})} placeholder="Enter your API key" /></label><label>API Secret<input required type="password" autoComplete="off" value={form.api_secret} onChange={e => setForm({...form, api_secret: e.target.value})} placeholder="Enter your API secret" /></label><div className="field-heading">Request Token{form.api_key.trim() && <a href={`https://kite.zerodha.com/connect/login?v=3&api_key=${encodeURIComponent(form.api_key.trim())}`} target="_blank" rel="noreferrer">Authorize on Kite ↗</a>}</div><input aria-label="Request Token" required type="password" autoComplete="off" value={form.request_token} onChange={e => setForm({...form, request_token: e.target.value})} placeholder="Paste a fresh request token"/><p className="hint">Authorize on Kite, then copy request_token from the redirected URL.</p>{error && <div role="alert" className="error">{error}</div>}<button className="primary" disabled={busy}>{busy ? 'Connecting…' : 'Login →'}</button><p className="security">Your session stays encrypted on this computer. Code reloads keep you signed in until Kite expires the session.</p></form></section></main>;
  const expired=()=>{setProfile(null);setError('Kite session expired. Please authorize again.');};
  return <div className="shell"><aside>{brand}<p className="nav-label">WORKSPACE</p><button className="nav-item">◫ <span>Dashboard</span><span className="nav-dot"/></button><div className="sidebar-bottom"><span className="status-dot"/> Kite account connected<small>Personal · Local development</small></div></aside><main className="workspace"><header><span>Workspace <span className="slash">/</span> Dashboard</span><div className="header-right"><span className="avatar">{profile.user_name?.charAt(0) || 'U'}</span><button onClick={logout} disabled={busy}>Sign out</button></div></header><section className="content"><div className="title-row"><div><p className="eyebrow">ACCOUNT OVERVIEW</p><h1>Your workspace</h1><p className="muted">A connected account. A focused starting point.</p></div><span className="pill"><span className="status-dot"/> Connected to Kite</span></div><nav className="tabs" aria-label="Dashboard tabs">{['User', 'Overview', 'Signals', 'Stock View'].map(name => <button key={name} aria-current={tab === name ? 'page' : undefined} className={tab === name ? 'selected' : ''} onClick={() => { setTab(name); if (name === 'User') refresh(); }}>{name}</button>)}</nav>{error && <div className="error" role="alert">{error}</div>}{tab === 'User' ? <><div className="section-title"><div><h2>User profile</h2><p className="muted">Account details retrieved directly from Zerodha.</p></div><button onClick={() => refresh()} disabled={busy}>{busy ? 'Refreshing…' : '↻ Refresh'}</button></div><div className="profile-card"><div className="profile-heading"><div className="avatar large">{profile.user_name?.charAt(0) || 'U'}</div><div><h2>{profile.user_name || 'Not provided'}</h2><span className="muted">Zerodha account</span></div><span className="outline-pill">VERIFIED SESSION</span></div><div className="identity-grid"><div><p className="eyebrow">USER NAME</p><strong>{profile.user_name || 'Not provided'}</strong></div><div><p className="eyebrow">USER ID</p><strong className="mono">{profile.user_id || 'Not provided'}</strong></div></div></div><div className="card-grid">{[['Products', profile.products], ['Exchanges', profile.exchanges]].map(([title, items]) => <article className="card" key={title}><div className="card-title"><h2>{title}</h2><span className="count">{items?.length || 0}</span></div><p className="muted">{title === 'Products' ? 'Product types enabled for your account.' : 'Exchanges available through your account.'}</p><div className="chips">{items?.length ? items.map(item => <span className="chip" key={item}>{item}</span>) : <span className="muted">None provided by Kite.</span>}</div></article>)}</div></> : tab === 'Overview' ? <Suspense fallback={<div className="card">Loading market overview…</div>}><Overview onSessionExpired={expired} /></Suspense> : tab === 'Signals' ? <Signals onSessionExpired={expired} /> : <Suspense fallback={<div className="card">Loading stock research…</div>}><StockView onSessionExpired={expired}/></Suspense>}<footer><span>Ankit Kumar / Personal dashboard</span><span>Session credentials stay on the backend</span></footer></section></main></div>;
}
createRoot(document.getElementById('root')).render(<App/>);
