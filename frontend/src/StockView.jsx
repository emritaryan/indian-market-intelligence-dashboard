import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import './fundamentals.css';
echarts.use([BarChart, CandlestickChart, LineChart, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const fmt=(v,d=2)=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:d,minimumFractionDigits:d});
const compact=v=>v==null?'—':new Intl.NumberFormat('en-IN',{notation:'compact',maximumFractionDigits:2}).format(v);
const crores=v=>v==null?'—':`₹${Number(v/1e7).toLocaleString('en-IN',{maximumFractionDigits:2})}Cr`;
const pct=v=>v==null?'—':`${v>0?'+':''}${Number(v).toFixed(2)}%`;
const tone=v=>v==null||v===0?'':v>0?'positive':'negative';
const ranges=['1M','3M','6M','YTD','1Y','3Y','5Y','MAX'];

function PriceChart({rows=[]}){
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current||!rows.length)return;
    const chart=echarts.init(ref.current);const dates=rows.map(r=>r.date);
    chart.setOption({animation:false,legend:{top:0,right:10,textStyle:{color:'#94a1b7',fontSize:10},data:['SMA 10','SMA 20','SMA 50','SMA 100']},
      tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:'#172232',borderColor:'#33445a',textStyle:{color:'#edf2fa'}},
      axisPointer:{link:[{xAxisIndex:'all'}]},grid:[{left:66,right:18,top:40,height:'63%'},{left:66,right:18,top:'76%',height:'14%'}],
      xAxis:[{type:'category',data:dates,boundaryGap:true,axisLine:{lineStyle:{color:'#253044'}},axisLabel:{show:false}},
        {type:'category',gridIndex:1,data:dates,boundaryGap:true,axisLine:{lineStyle:{color:'#253044'}},axisLabel:{color:'#94a1b7',fontSize:10,hideOverlap:true}}],
      yAxis:[{scale:true,axisLabel:{color:'#94a1b7',fontSize:10},splitLine:{lineStyle:{color:'#202b3b'}}},
        {scale:true,gridIndex:1,axisLabel:{color:'#94a1b7',fontSize:9,formatter:v=>compact(v)},splitLine:{show:false}}],
      dataZoom:[{type:'inside',xAxisIndex:[0,1],start:0,end:100}],
      series:[{name:'Price',type:'candlestick',data:rows.map(r=>[r.open,r.close,r.low,r.high]),itemStyle:{color:'#47d7a7',color0:'#f06d83',borderColor:'#47d7a7',borderColor0:'#f06d83'}},
        ...[10,20,50,100].map((p,i)=>({name:`SMA ${p}`,type:'line',data:rows.map(r=>r[`sma${p}`]),showSymbol:false,smooth:false,lineStyle:{width:i<2?1.6:1,color:['#75a7ff','#f2c66d','#b98cff','#7ccad1'][i]},connectNulls:false})),
        {name:'Volume',type:'bar',xAxisIndex:1,yAxisIndex:1,data:rows.map(r=>({value:r.volume,itemStyle:{color:r.close>=r.open?'#3a8c78':'#86495a'}}))}]});
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);return()=>{observer.disconnect();chart.dispose();};
  },[rows]);
  return rows.length?<div ref={ref} className="stock-price-chart" role="img" aria-label="Price candlestick and volume chart"/>:<div className="stock-price-chart ov-empty">Price history unavailable</div>;
}

function DeliveryChart({rows=[]}){
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current||!rows.length)return;const chart=echarts.init(ref.current);
    chart.setOption({animation:false,legend:{top:0,textStyle:{color:'#94a1b7'},data:['Total traded','Delivery']},tooltip:{trigger:'axis',backgroundColor:'#172232',borderColor:'#33445a',textStyle:{color:'#edf2fa'}},
      grid:{top:40,left:60,right:15,bottom:35},xAxis:{type:'category',data:rows.map(r=>r.date.slice(5)),axisLabel:{color:'#94a1b7'},axisLine:{lineStyle:{color:'#253044'}}},
      yAxis:{type:'value',axisLabel:{color:'#94a1b7',formatter:v=>compact(v)},splitLine:{lineStyle:{color:'#202b3b'}}},
      series:[{name:'Total traded',type:'bar',data:rows.map(r=>r.total_volume),itemStyle:{color:'#807bd5'},barMaxWidth:24},{name:'Delivery',type:'bar',data:rows.map(r=>r.delivery_volume),itemStyle:{color:'#55a9d8'},barMaxWidth:24}]});
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);return()=>{observer.disconnect();chart.dispose();};
  },[rows]);
  return rows.length?<div ref={ref} className="delivery-chart" role="img" aria-label="Last seven sessions total traded and delivery volume"/>:<div className="delivery-chart ov-empty">Delivery archive unavailable</div>;
}

export default function StockView({onSessionExpired}){
  const [stocks,setStocks]=useState([]),[query,setQuery]=useState('RELIANCE'),[symbol,setSymbol]=useState('RELIANCE'),[range,setRange]=useState('1Y');
  const [data,setData]=useState(null),[loading,setLoading]=useState(true),[chartLoading,setChartLoading]=useState(false),[error,setError]=useState('');
  const chartRequest=useRef(null);
  useEffect(()=>{fetch('/api/stocks',{cache:'no-store'}).then(async r=>{if(r.status===401){onSessionExpired();return;}if(!r.ok)throw new Error('Could not load the Nifty 100 stock list.');return r.json();}).then(d=>d&&setStocks(d.items)).catch(e=>setError(e.message));},[]);
  useEffect(()=>{const controller=new AbortController();chartRequest.current?.abort();setLoading(true);setData(null);setError('');fetch(`/api/stocks/${encodeURIComponent(symbol)}?range=${range}`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(r.status===401){onSessionExpired();return null;}const body=await r.json();if(!r.ok)throw new Error(body.detail||'Stock data unavailable.');return body;}).then(body=>{if(body)setData(body);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>setLoading(false));return()=>controller.abort();},[symbol]);
  const suggestions=useMemo(()=>{const needle=query.trim().toLowerCase();return needle?stocks.filter(s=>s.symbol.toLowerCase().includes(needle)||s.company.toLowerCase().includes(needle)).slice(0,7):[];},[stocks,query]);
  const select=item=>{setQuery(item.symbol);setSymbol(item.symbol);};
  const submit=e=>{e.preventDefault();const exact=stocks.find(s=>s.symbol.toLowerCase()===query.trim().toLowerCase())||suggestions[0];if(exact)select(exact);else setError('Choose a company from the Nifty 100 search results.');};
  const changeRange=async nextRange=>{
    if(nextRange===range||chartLoading||!data)return;
    const previousRange=range,controller=new AbortController();
    chartRequest.current?.abort();chartRequest.current=controller;setRange(nextRange);setChartLoading(true);setError('');
    try{
      const response=await fetch(`/api/stocks/${encodeURIComponent(symbol)}/chart?range=${nextRange}`,{cache:'no-store',signal:controller.signal});
      if(response.status===401){onSessionExpired();return;}
      const body=await response.json();if(!response.ok)throw new Error(body.detail||'Chart data unavailable.');
      setData(current=>current?{...current,range:body.range,series:body.series}:current);
    }catch(e){if(e.name!=='AbortError'){setRange(previousRange);setError(e.message);}}
    finally{if(chartRequest.current===controller){chartRequest.current=null;setChartLoading(false);}}
  };
  const quote=data?.quote||{},tech=data?.technical||{},fund=data?.fundamentals,metrics=fund?.metrics||{};
  const delivery=data?.delivery||[],total=delivery.reduce((n,r)=>n+r.total_volume,0),delivered=delivery.reduce((n,r)=>n+r.delivery_volume,0);
  const metricRows=[['Market Cap',metrics.market_cap,'crores'],['P/E Ratio (TTM)',metrics.stock_pe],['P/B Ratio',metrics.pb_ratio],['Debt to Equity',metrics.debt_to_equity],['ROE',metrics.roe,'percent'],['EPS (TTM)',metrics.eps_ttm,'rupees'],['Dividend Yield',metrics.dividend_yield,'percent'],['Book Value',metrics.book_value,'rupees']];
  return <section className="stock-view"><div className="stock-top"><div><p className="eyebrow">SINGLE STOCK RESEARCH</p><h2>Stock View</h2><p className="muted">Search the Nifty 100 and inspect price, momentum, participation, and fundamentals.</p></div><form className="stock-search" onSubmit={submit}><label htmlFor="stock-query">Search stock</label><div><input id="stock-query" value={query} onChange={e=>setQuery(e.target.value)} autoComplete="off" placeholder="Ticker or company name"/><button className="primary">View stock</button></div>{query&&suggestions.length>0&&query!==symbol&&<div className="stock-suggestions">{suggestions.map(item=><button type="button" key={item.symbol} onClick={()=>select(item)}><b>{item.symbol}</b><span>{item.company}</span></button>)}</div>}</form></div>
    {error&&<div className="error" role="alert">{error}</div>}
    {loading&&<div className="card stock-loading">Loading {symbol} market data…</div>}
    {data&&<>
      <article className="card stock-hero"><div><span className="ticker-line">{data.stock.symbol} · NSE</span><h2>{data.stock.company}</h2><p>{data.stock.sector}</p></div><div className="stock-last"><strong>₹{fmt(quote.price)}</strong><span className={tone(quote.change)}>{pct(quote.change)}</span></div><div className="stock-ohlc">{Object.entries(quote.ohlc||{}).map(([key,value])=><span key={key}><small>{key}</small><b>{fmt(value)}</b></span>)}</div></article>
      <article className="card price-card"><div className="card-title"><div><p className="eyebrow">PRICE & VOLUME TREND</p><h2>{data.stock.symbol} chart</h2></div><span className="outline-pill">KITE DAILY CANDLES</span></div><div className="range-tabs stock-ranges">{ranges.map(v=><button key={v} className={range===v?'active':''} disabled={chartLoading} onClick={()=>changeRange(v)}>{v}</button>)}</div><div className={`chart-shell ${chartLoading?'updating':''}`}><PriceChart rows={data.series}/>{chartLoading&&<div className="chart-updating"><span/>Updating chart…</div>}</div><p className="hint">Drag or scroll inside the chart to zoom. Daily OHLCV from Zerodha Kite; SMA lines use completed daily candles.</p></article>
      <section className="technical-section"><div className="section-title"><div><p className="eyebrow">TECHNICAL INDICATORS</p><h2>Momentum, trend & volatility</h2></div><span className={`verdict ${tech.verdict?.toLowerCase()}`}>{tech.verdict}</span></div><div className="technical-grid"><article className="card rsi-card"><span className="eyebrow">RSI · 14 DAYS</span><strong>{fmt(tech.rsi14,1)}</strong><div className="rsi-track"><i style={{width:`${Math.min(100,Math.max(0,tech.rsi14||0))}%`}}/></div><small>Oversold 30 · Neutral 50 · Overbought 70</small></article>{Object.entries(tech.moving_averages||{}).map(([period,value])=><article className="card ma-card" key={period}><span className="eyebrow">MOVING AVERAGE</span><strong>SMA {period}</strong><b>₹{fmt(value)}</b><small className={tone(quote.price&&value?(quote.price/value-1)*100:null)}>{quote.price&&value?`${pct((quote.price/value-1)*100)} vs price`:'Unavailable'}</small></article>)}<article className="card ma-card"><span className="eyebrow">TREND MOMENTUM</span><strong>MACD 12 · 26 · 9</strong><b className={tone(tech.macd?.histogram)}>₹{fmt(tech.macd?.line,2)}</b><small className={tone(tech.macd?.histogram)}>{tech.macd?.verdict||'Unavailable'} · signal {fmt(tech.macd?.signal,2)}</small></article><article className="card ma-card"><span className="eyebrow">VOLATILITY</span><strong>ATR · 14 DAYS</strong><b>₹{fmt(tech.atr14,2)}</b><small>{tech.atr_percent==null?'Unavailable':`${fmt(tech.atr_percent,2)}% of price`}</small></article></div><p className="hint">{tech.method} MACD highlights trend momentum; ATR measures recent price volatility. This rule is a dashboard summary, not investment advice.</p></section>
      <article className="card delivery-card"><div className="card-title"><div><p className="eyebrow">LAST 7 SESSIONS</p><h2>Traded volume vs delivery volume</h2></div><span className="outline-pill">OFFICIAL NSE ARCHIVE</span></div><div className="delivery-layout"><div className="delivery-summary"><span><i className="total-dot"/>Total traded volume <b>{compact(total)}</b></span><span><i className="delivery-dot"/>Delivery volume <b>{compact(delivered)}</b></span><hr/><div className="delivery-percent"><b>{total?`${fmt(delivered/total*100,2)}%`:'—'}</b><span>Delivery percentage</span></div></div><DeliveryChart rows={delivery}/></div></article>
      <section className="fundamentals"><div className="section-title"><div><p className="eyebrow">FUNDAMENTALS</p><h2>Company snapshot</h2><p className="muted">Current price from Kite with company fundamentals from Yahoo Finance. Missing source values remain blank.</p></div><span className={`provider-status ${fund?.status}`}>{fund?.status==='available'?'Yahoo + Kite':'Yahoo unavailable'}</span></div><div className="fund-grid">{metricRows.map(([label,value,type])=><article className="card" key={label}><span className="eyebrow">{label}</span><strong>{value==null?'—':type==='percent'?`${fmt(value,2)}%`:type==='crores'?crores(value):type==='rupees'?`₹${fmt(value,2)}`:fmt(value,2)}</strong></article>)}</div></section>
      <p className="hint stock-sources">Sources: price/technical indicators — {data.sources.price}; delivery — {data.sources.delivery}; fundamentals — {data.sources.fundamentals}.</p>
    </>}
  </section>;
}
