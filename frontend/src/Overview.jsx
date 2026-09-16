import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, TreemapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
echarts.use([LineChart, TreemapChart, GridComponent, TooltipComponent, CanvasRenderer]);

const fmt = v => v == null ? '—' : Number(v).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2});
const compact = v => v == null ? '—' : new Intl.NumberFormat('en-IN',{notation:'compact',maximumFractionDigits:1}).format(v);
const pct = v => v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
const tone = v => v == null || v === 0 ? '' : v > 0 ? 'positive' : 'negative';
const stamp = v => v ? new Date(v).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})+' IST' : 'Timestamp unavailable';
const ranges = ['1M','3M','6M','YTD','1Y','3Y','5Y','MAX'];

function cut(points, range){
  if(!points?.length || range==='MAX') return points||[];
  const end=new Date(points.at(-1).date+'T00:00:00Z');
  let start;
  if(range==='YTD') start=new Date(Date.UTC(end.getUTCFullYear(),0,1));
  else {start=new Date(end);start.setUTCDate(start.getUTCDate()-({"1M":31,"3M":93,"6M":186,"1Y":365,"3Y":1095,"5Y":1825}[range]||365));}
  return points.filter(p=>new Date(p.date+'T00:00:00Z')>=start);
}

function Trend({points=[],small=false,color='#79e0b7'}) {
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current || !points.length)return;
    const chart=echarts.init(ref.current);
    chart.setOption({animation:false,grid:small?{top:7,bottom:2,left:0,right:0}:{top:20,bottom:36,left:66,right:16},
      tooltip:{show:true,trigger:'axis',backgroundColor:'#172232',borderColor:'#33445a',textStyle:{color:'#edf2fa'},valueFormatter:fmt},
      xAxis:{type:'category',data:points.map(p=>p.date),boundaryGap:false,show:!small,axisLabel:{color:'#94a1b7',fontSize:10,hideOverlap:true},axisLine:{lineStyle:{color:'#253044'}},axisTick:{show:false}},
      yAxis:{type:'value',scale:true,show:!small,axisLabel:{color:'#94a1b7',fontSize:10},splitLine:{lineStyle:{color:'#202b3b'}}},
      series:[{name:'Price',type:'line',showSymbol:false,data:points.map(p=>p.close),lineStyle:{width:2,color},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'42'},{offset:1,color:color+'00'}])}}]});
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
    return ()=>{observer.disconnect();chart.dispose();};
  },[points,small,color]);
  return points.length?<div ref={ref} className={small?'ov-mini':'ov-chart'} role="img" aria-label={`Price trend, ${points.length} sessions`}/>:<div className={small?'ov-mini ov-empty':'ov-chart ov-empty'}>History unavailable</div>;
}

function Heatmap({data,large=false}){
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current||!data.length)return;
    const chart=echarts.init(ref.current);
    chart.setOption({animationDuration:350,tooltip:{formatter:p=>p.data?.symbol?`<b>${p.data.company}</b><br/>${p.data.symbol} · ${pct(p.data.change)}<br/>Session traded value ${compact(p.data.rawValue)}`:`<b>${p.name}</b>`},
      series:[{type:'treemap',roam:large,nodeClick:false,breadcrumb:{show:false},visibleMin:10,
        label:{show:true,color:'#f3f6fb',formatter:p=>p.data.symbol?`${p.data.symbol}\n${pct(p.data.change)}`:p.name,fontSize:11,lineHeight:15},
        upperLabel:{show:true,height:27,color:'#fff',fontWeight:600},itemStyle:{borderColor:'#0b1019',borderWidth:2,gapWidth:1},
        levels:[{itemStyle:{borderWidth:3,gapWidth:3}},{upperLabel:{show:true},itemStyle:{borderWidth:1,gapWidth:1}}],data}]});
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
    return()=>{observer.disconnect();chart.dispose();};
  },[data,large]);
  return <div ref={ref} className={large?'ov-heatmap large-map':'ov-heatmap'} role="img" aria-label="Nifty 100 sector heatmap"/>;
}

const RangeTabs=({value,onChange})=><div className="range-tabs">{ranges.map(v=><button key={v} className={value===v?'active':''} onClick={()=>onChange(v)}>{v}</button>)}</div>;

export default function Overview({onSessionExpired}) {
  const [quotes,setQuotes]=useState(null),[history,setHistory]=useState(null),[macro,setMacro]=useState(null),[ipos,setIpos]=useState(null);
  const [errors,setErrors]=useState({}),[reload,setReload]=useState(0),[range,setRange]=useState('6M'),[leaders,setLeaders]=useState('Gainers'),[expanded,setExpanded]=useState(false);
  const expire=useRef(onSessionExpired);expire.current=onSessionExpired;
  useEffect(()=>{
    let stopped=false;const timers=new Set();const controller=new AbortController();
    async function poll(kind,setter,delay){
      try{const response=await fetch(`/api/overview/${kind}`,{cache:'no-store',signal:controller.signal});
        if(response.status===401){if(!stopped)expire.current();return;}
        if(!response.ok)throw new Error(`${kind==='quotes'?'Kite quotes':kind==='history'?'Historical charts':kind==='ipos'?'IPO feed':'Commodity/FX feed'} unavailable. Retry shortly.`);
        const data=await response.json();if(!stopped){setter(data);setErrors(old=>({...old,[kind]:null}));}
        if(kind==='quotes')delay=Math.max(15,data.config?.refresh_seconds||15)*1000;
      }catch(e){if(!stopped&&!controller.signal.aborted)setErrors(old=>({...old,[kind]:e.message}));}
      if(!stopped){const timer=setTimeout(()=>{timers.delete(timer);poll(kind,setter,delay);},delay);timers.add(timer);}
    }
    poll('quotes',setQuotes,15000);poll('history',setHistory,900000);poll('macro',setMacro,300000);poll('ipos',setIpos,900000);
    return()=>{stopped=true;controller.abort();timers.forEach(clearTimeout);};
  },[reload]);

  const nifty=useMemo(()=>cut(history?.nifty,range),[history,range]);
  const stocks=useMemo(()=>(quotes?.universe||[]).map(item=>({...item,...quotes?.quotes[item.symbol]})).filter(item=>item.change!=null),[quotes]);
  const gainers=useMemo(()=>[...stocks].sort((a,b)=>b.change-a.change).slice(0,10),[stocks]);
  const losers=useMemo(()=>[...stocks].sort((a,b)=>a.change-b.change).slice(0,10),[stocks]);
  const heatmap=useMemo(()=>{
    const groups={};for(const item of stocks)(groups[item.sector]||=[]).push(item);
    const color=value=>{const strength=Math.min(Math.abs(value||0)/4,1);return value>0?`rgba(${42-Math.round(15*strength)},${103+Math.round(55*strength)},${78-Math.round(15*strength)},1)`:`rgba(${110+Math.round(65*strength)},${55-Math.round(15*strength)},${72-Math.round(5*strength)},1)`;};
    return Object.entries(groups).map(([name,items])=>({name,value:items.reduce((n,i)=>n+(i.traded_value||1),0),children:items.map(i=>({name:i.symbol,symbol:i.symbol,company:i.company,change:i.change,rawValue:i.traded_value||0,value:Math.max(i.traded_value||0,1),itemStyle:{color:color(i.change)}}))}));
  },[stocks]);
  const nq=quotes?.quotes?.['NIFTY 50'], nohlc=nq?.ohlc||{};

  return <section className="overview"><div className="ov-heading"><div><p className="eyebrow">MARKET OVERVIEW</p><h2>The market, at a glance.</h2><p className="muted">Nifty 100 breadth, sector movement, and the global prices around it.</p></div><button onClick={()=>setReload(n=>n+1)}>↻ Refresh</button></div>
    <div className="ov-status"><strong className={quotes?.market.is_open?'positive':''}>{quotes?.market.is_open?'● ':'◷ '}{quotes?.market.label||'Checking market status…'}</strong><span>{quotes?stamp(quotes.market.ist_time):'IST'} · NSE cash 09:15–15:30</span><span>{quotes?.market.is_open?`Kite quotes refresh every ${Math.max(15,quotes.config.refresh_seconds)}s`:'Latest completed/current-session data'}</span></div>
    {Object.values(errors).filter(Boolean).map(error=><div role="alert" className="error" key={error}>{error}</div>)}
    {!quotes&&!errors.quotes&&<div className="card ov-empty">Connecting to Kite quotes…</div>}
    {quotes&&<>
      <div className="ov-section"><div className="ov-indices">{quotes.config.indices.map(item=>{const q=quotes.quotes[item.symbol],series=history?.index_history?.[item.symbol]||[],latest=series.at(-1),prior=series.at(-2),useHistory=!quotes.market.is_open&&latest&&prior,price=useHistory?latest.close:q?.price,cardChange=useHistory?(latest.close/prior.close-1)*100:q?.change,absoluteChange=useHistory?latest.close-prior.close:q?.absolute_change,sessionStamp=useHistory?`${latest.date}T15:30:00+05:30`:q?.timestamp;return <article className="ov-index" key={item.symbol}><div className="ov-index-head"><div><p className="eyebrow">{item.name}</p><strong>{fmt(price)}</strong></div><div className={tone(cardChange)}><b>{pct(cardChange)}</b><small>{absoluteChange>0?'+':''}{fmt(absoluteChange)}</small></div></div><Trend points={series.slice(-60)} small color={cardChange<0?'#f06d83':'#79e0b7'}/><span className="ov-timestamp">{stamp(sessionStamp)}</span></article>})}</div></div>
      <div className="ov-section ov-chart-grid"><article className="card market-direction"><div className="card-title"><div><p className="eyebrow">MARKET DIRECTION</p><h2>Nifty 50</h2></div><span className="outline-pill">{range}</span></div><RangeTabs value={range} onChange={setRange}/>{history?<Trend points={nifty}/>:<div className="ov-chart ov-empty">Loading Nifty history…</div>}<div className="market-stats">{[['Open',nohlc.open],['High',nohlc.high],['Low',nohlc.low],['Prev close',nohlc.close],['52-wk high',history?.stats?.high_52w],['52-wk low',history?.stats?.low_52w]].map(([k,v])=><span key={k}><small>{k}</small><b>{fmt(v)}</b></span>)}</div></article>
      <article className="card leaders"><div className="leaders-tabs">{['Gainers','Losers'].map(name=><button key={name} className={leaders===name?'active':''} onClick={()=>setLeaders(name)}>{name}</button>)}</div><p className="hint">Top 10 · Nifty 100 · latest Kite session</p><div className="leader-list">{(leaders==='Gainers'?gainers:losers).map((item,i)=><div className="leader-row" key={item.symbol}><span className="leader-rank">{i+1}</span><div><b>{item.symbol}</b><small title={item.company}>{item.company}</small></div><div><b>{fmt(item.price)}</b><span className={tone(item.change)}>{pct(item.change)}</span></div></div>)}</div></article></div>
      <section className="ov-section"><div className="section-title"><div><p className="eyebrow">SECTOR MAP</p><h2>Nifty 100 heatmap</h2><p className="muted">Tile size uses current-session traded value; colour shows change from previous close.</p></div><button onClick={()=>setExpanded(true)}>⛶ Expand</button></div><article className="card heatmap-card"><Heatmap data={heatmap}/><div className="heat-legend"><span>−4%</span><i/><i/><i/><i/><i/><span>+4%</span><em>{stocks.length} stocks · {heatmap.length} sectors</em></div></article></section>
      <section className="ov-section"><div className="section-title"><div><p className="eyebrow">BEYOND EQUITIES</p><h2>Commodities, currency & open IPOs</h2></div></div><div className="macro-ipo-grid"><div className="ov-macro">{(macro?.items||quotes.config.macro||[]).map(item=><article className="card" key={item.symbol}><div className="card-title"><h3>{item.name}</h3><span className={tone(item.change)}>{pct(item.change)}</span></div><strong className="ov-price">{fmt(item.price)}</strong><span className="hint">{item.unit} · rolling 7 sessions</span>{macro?<Trend points={item.series?.slice(-7)||[]} small color={item.change<0?'#f19aab':'#79e0b7'}/>:<div className="ov-mini ov-empty">Loading…</div>}<p className="ov-timestamp">Hover the trend for date and price · {item.error||stamp(item.timestamp)}</p></article>)}</div><article className="card ipo-card"><div className="card-title"><div><p className="eyebrow">OPEN FOR SUBSCRIPTION</p><h2>Current IPOs</h2></div><span className="outline-pill">NSE</span></div>{ipos?.error&&<p className="muted">{ipos.error}</p>}{!ipos&&<p className="muted">Loading current issues…</p>}{ipos&&!ipos.items.length&&!ipos.error&&<p className="muted">No NSE IPO is currently open.</p>}<div className="ipo-list">{ipos?.items.map(item=><div key={item.symbol}><div><b>{item.company}</b><small>{item.symbol} · {item.price_band}</small></div><span><small>Closes</small><b>{item.close_date}</b></span></div>)}</div><p className="hint">Official NSE current-issue feed · refreshed every 15 minutes</p></article></div><p className="hint">Commodity futures and USD/INR are from Yahoo Finance and may be delayed. Indian equity/index prices are from Kite.</p></section>
    </>}
    {expanded&&<div className="heat-modal" role="dialog" aria-modal="true" aria-label="Expanded Nifty 100 heatmap"><div><header><span><b>Nifty 100 sector heatmap</b><small>Size = session traded value · colour = daily move</small></span><button onClick={()=>setExpanded(false)}>Close ×</button></header><Heatmap data={heatmap} large/></div></div>}
    {history?.warnings?.length>0&&<details className="scan-warning"><summary>{history.warnings.length} historical feed(s) unavailable</summary><ul>{history.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>}
    <p className="hint">Kite quote request: {stamp(quotes?.fetched_at)}. No simulated prices.</p></section>;
}
