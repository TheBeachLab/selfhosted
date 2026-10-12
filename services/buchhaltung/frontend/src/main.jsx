import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const PAGE = {invoices: 'Facturas', expenses: 'Gastos', bank: 'Banco', eur: 'EÜR', vat: 'IVA', settings: 'Configuración'};
const STATUS = {draft:'Borrador', needs_review:'Por revisar', issued:'Emitida', reviewed:'Revisado', private:'Privado', void:'Descartado', cancelled:'Anulado'};
const activityPending = row => row.data.source_activity_pending || row.data.source_unsupported?.includes('Centro de coste sin actividad reconocida.');
const activityLabel = (row, activities) => row.state==='private' ? 'Privado' : activityPending(row) ? 'Pendiente de asignar' : [...new Set(row.data.lines.map(line=>activities[line.activity]))].join(' / ');
const EMPTY_PARTY = {name:'',street:'',postcode:'',city:'',country:'DE',email:'',phone:'',vat_id:'',tax_number:'',iban:'',buyer_reference:''};
const euro = cents => new Intl.NumberFormat('de-DE', {style:'currency', currency:'EUR'}).format(cents / 100);
const inputAmount = cents => (cents / 100).toFixed(2).replace('.', ',');
const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin'}).format(new Date());
const plusDays = (value, n) => {const d = new Date(value + 'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
const displayDate = value => value?.slice(0,10).split('-').reverse().join('.') || '—';
function parseAmount(value) {
  const raw = String(value).trim().replace(',', '.');
  if (!/^\d+(\.\d{0,2})?$/.test(raw)) throw new Error('Usa un importe positivo con hasta dos decimales.');
  const [whole, decimals=''] = raw.split('.');
  const result = Number(whole) * 100 + Number(decimals.padEnd(2,'0'));
  if (!Number.isSafeInteger(result) || result > 10000000000) throw new Error('Importe fuera de rango.');
  return result;
}
async function api(path, options={}) {
  const isForm = options.body instanceof FormData;
  const response = await fetch('/api/' + path, {...options, credentials:'same-origin', headers:{...(!isForm ? {'Content-Type':'application/json'} : {}), ...options.headers}, body:options.body && !isForm ? JSON.stringify(options.body) : options.body});
  if (response.redirected || response.headers.get('content-type')?.includes('text/html')) throw new Error('La sesión ha terminado. Recarga e inicia sesión con tu passkey.');
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(x=>x.msg).join(' · ') : 'No se pudo completar la operación.');
  return data;
}

function Icon({name, size=21}) {
  const paths = {
    invoices: <><path d="M7 3h8l4 4v14H5V3h2Z"/><path d="M14 3v5h5M8 12h8M8 16h6"/></>,
    expenses: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z"/><path d="M9 7h6M9 11h6M9 15h3"/></>,
    bank: <><path d="m3 8 9-5 9 5M4 9h16M6 10v8M12 10v8M18 10v8M3 21h18M4 18h16"/></>,
    eur: <><path d="M4 20h16M7 16V9M12 16V4M17 16v-5"/></>,
    vat: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M14 11h2M8 15h2M14 15h2M8 18h2M14 18h2"/></>,
    settings: <><path d="m10 3-1 3-3 1-2 3 2 2-1 3 3 2 3-1 2 2 3-2 1-3 3-1v-4l-3-1-1-3h-4Z"/><circle cx="12" cy="12" r="3"/></>,
    user: <><circle cx="12" cy="8" r="3"/><path d="M6 21v-3a6 6 0 0 1 12 0v3"/></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4M4 16v5h16v-5"/></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
function Field({label, children, className=''}) {return <label className={'field '+className}><span>{label}</span>{children}</label>;}
function Empty({title, description, columns}) {return <tr><td className="empty-cell" colSpan={columns}><div className="empty"><strong>{title}</strong><p>{description}</p></div></td></tr>;}
function Notice({children, error=false}) {return children ? <div role={error?'alert':'status'} className={'notice '+(error?'error':'')}>{children}</div> : null;}
function Blockers({items=[]}) {return items.length ? <div className="review-notice"><strong>Revisión pendiente</strong><ul>{items.slice(0,5).map(x=><li key={x}>{x}</li>)}</ul>{items.length>5 ? <details><summary>{items.length-5} avisos más</summary><ul>{items.slice(5).map(x=><li key={x}>{x}</li>)}</ul></details> : null}</div> : <Notice>Preparada para revisión final. No se ha enviado.</Notice>;}
function ImportStatus({value}) {
  if (value.state==='scheduled') {const overdue = new Date(value.at)<new Date();return <span>Histórico 2026: {overdue?'importación pendiente desde las 20:00':'importación programada para las 20:00'}</span>;}
  if (value.state==='running') return <span>Histórico 2026: importación en curso.</span>;
  if (value.state==='complete') return <span>Histórico 2026: importado y verificado. Revisa las clasificaciones fiscales.</span>;
  return <span>Histórico 2026: importación con avisos. Consulta Configuración.</span>;
}

function App() {
  const [page, setPage] = useState('expenses');
  const [boot, setBoot] = useState(null);
  const [records, setRecords] = useState([]);
  const [bank, setBank] = useState([]);
  const [editor, setEditor] = useState(null);
  const [detail, setDetail] = useState(null);
  const [menu, setMenu] = useState(false);
  const [filter, setFilter] = useState('all');
  const [period, setPeriod] = useState('q4');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const range = period==='q4' ? 'start=2026-10-01&end=2026-12-31' : 'start=2026-01-01&end=2026-12-31';
  async function refresh() {
    const [context, rows, movements] = await Promise.all([api('bootstrap'), api('records?'+range), api('bank?'+range)]);
    setBoot(context);setRecords(rows);setBank(movements);
  }
  useEffect(()=>{let active=true;Promise.all([api('bootstrap'),api('records?'+range),api('bank?'+range)]).then(([context,rows,movements])=>{if(active){setBoot(context);setRecords(rows);setBank(movements);setError('');}}).catch(e=>active && setError(e.message));return ()=>{active=false;};},[range]);
  async function act(fn, success='Guardado.') {
    setBusy(true);setError('');setMessage('');
    try {const result=await fn();await refresh();setMessage(success);return result;} catch(e) {setError(e.message);return null;} finally {setBusy(false);}
  }
  function navigate(next) {setPage(next);setEditor(null);setDetail(null);setMenu(false);setError('');setMessage('');}
  async function upload(file) {
    if (!file) return;
    const form=new FormData();form.append('file',file);
    const result=await act(()=>api('documents',{method:'POST',body:form}), 'Justificante guardado. Completa el gasto.');
    if (result) setEditor({kind:'expense',documents:[result]});
  }
  async function openDetail(row) {try {setDetail(await api('records/'+row.id));setError('');} catch(e) {setError(e.message);}}
  const visible=records.filter(row=>row.state!=='void' && (page==='invoices' ? row.kind==='invoice' : ['expense','income','credit_note','asset','tax_payment','tax_refund'].includes(row.kind))).filter(row=>filter==='all' || (row.state!=='private' && !activityPending(row) && row.data.lines.some(line=>line.activity===filter)));
  const title=editor ? editor.kind==='invoice' ? 'Nueva factura' : editor.id ? 'Revisar gasto' : 'Nuevo gasto' : PAGE[page];
  return <div className="app">
    <aside className={'sidebar '+(menu?'open':'')} inert={detail?true:undefined}>
      <a className="brand" href="/" onClick={e=>{e.preventDefault();navigate('expenses');}}><strong>Beach Lab</strong><span>Buchhaltung</span></a>
      <nav aria-label="Contabilidad">{Object.entries(PAGE).map(([key,label])=><button className={'nav-item '+(key===page?'active':'')} key={key} onClick={()=>navigate(key)} aria-current={key===page?'page':undefined}><Icon name={key}/>{label}</button>)}</nav>
    </aside>
    <div className="workspace" inert={detail?true:undefined}>
      <header className="topbar"><button className="icon-button mobile-menu" aria-label={menu?'Cerrar menú':'Abrir menú'} onClick={()=>setMenu(!menu)}><Icon name={menu?'close':'menu'}/></button><span className="mobile-brand">Buchhaltung</span><div className="account"><span>2026 · {period==='q4'?'T4':'Año'}</span><span className="account-divider"/><button onClick={()=>navigate('settings')} className="user-button" aria-label="Configuración de Fran"><Icon name="user"/>Fran<span aria-hidden="true">⌄</span></button></div></header>
      <main>
        <Notice error>{error}</Notice><Notice>{message}</Notice>
        {!boot ? <p className="loading">{error?'No se ha podido cargar la contabilidad.':'Cargando contabilidad…'}</p> : <>
          <div className="page-heading"><h1>{title}</h1>{editor ? <button className="secondary" onClick={()=>setEditor(null)} disabled={busy}>Volver</button> : ['expenses','invoices'].includes(page) ? <button className="primary" onClick={()=>setEditor({kind:page==='invoices'?'invoice':'expense'})}>+ {page==='invoices'?'Nueva factura':'Nuevo gasto'}</button> : null}</div>
          {editor ? <RecordEditor key={editor.id || editor.documents?.[0]?.id || editor.kind} initial={editor} boot={boot} busy={busy} onSave={async payload=>{const result=await act(()=>api('records'+(editor.id?'/'+editor.id:''),{method:editor.id?'PUT':'POST',body:payload}),'Borrador guardado.');if(result){setEditor(null);setDetail(result);}}} onUpload={async file=>{const form=new FormData();form.append('file',file);return act(()=>api('documents',{method:'POST',body:form}),'Justificante guardado.');}} onContact={async value=>act(()=>api('contacts',{method:'POST',body:value}),'Cliente guardado.')}/> : <>
          {['expenses','invoices'].includes(page) ? <>
            <div className="filters"><Field label="Actividad"><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Todas</option>{Object.entries(boot.activities).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></Field><Field label="Periodo"><select value={period} onChange={e=>setPeriod(e.target.value)}><option value="q4">T4 2026</option><option value="year">Todo 2026</option></select></Field></div>
            <div className="table-wrap"><table><thead><tr>{(page==='expenses'?['Fecha','Proveedor','Actividad','Base','IVA','Total','Estado']:['Fecha','Número / Cliente','Actividad','Base','IVA','Total','Estado']).map((label,i)=><th key={label} className={i>=3&&i<=5?'amount':''}>{label}</th>)}</tr></thead><tbody>{visible.length ? visible.map(row=><tr key={row.id}><td>{displayDate(row.date)}</td><td><button className="table-link" onClick={()=>openDetail(row)}>{page==='invoices' ? (row.number || 'Borrador')+' · '+(boot.contacts.find(c=>c.id===row.data.party_id)?.name || row.data.party_name || 'Cliente') : row.data.party_name || row.data.reference || 'Sin proveedor'}</button></td><td className="activity-cell">{activityLabel(row,boot.activities)}</td><td className="amount">{euro(row.net)}</td><td className="amount">{euro(row.tax)}</td><td className="amount strong">{euro(row.total)}</td><td><span className={'badge '+(row.state==='needs_review'?'warning':'')}>{STATUS[row.state] || row.state}</span></td></tr>) : <Empty columns={7} title={page==='expenses'?'Todavía no hay gastos.':'Todavía no hay facturas.'} description={page==='expenses'?'Añade un justificante para empezar.':'Crea una factura para empezar.'}/>}</tbody></table></div>
            {page==='expenses' ? <UploadBand onFile={upload} disabled={busy}/> : null}
          </> : null}
          {page==='bank' ? <BankPage boot={boot} rows={bank} act={act} busy={busy}/> : null}
          {page==='eur' ? <ReportPage type="eur" act={act} boot={boot}/> : null}
          {page==='vat' ? <ReportPage type="vat" act={act} boot={boot}/> : null}
          {page==='settings' ? <Settings boot={boot} act={act} busy={busy}/> : null}
          </>}
          <footer><ImportStatus value={boot.import}/></footer>
        </>}
      </main>
    </div>
    {detail ? <RecordDetail row={detail} boot={boot} busy={busy} onClose={()=>setDetail(null)} onEdit={()=>{setEditor({...detail.data,...detail,id:detail.id,kind:detail.kind,documents:detail.documents});setDetail(null);}} act={act} onChanged={async ()=>setDetail(await api('records/'+detail.id))}/> : null}
  </div>;
}

function UploadBand({onFile, disabled}) {
  const input=useRef(null);const [dragging,setDragging]=useState(false);
  return <div className={'upload-band '+(dragging?'dragging':'')} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);if(!disabled)onFile(e.dataTransfer.files[0]);}}><div><span>Arrastra un PDF, XML o imagen</span></div><button className="secondary" disabled={disabled} onClick={()=>input.current.click()}>Seleccionar archivo</button><input className="visually-hidden" ref={input} type="file" accept=".pdf,.xml,.jpg,.jpeg,.png" aria-label="Seleccionar justificante" onChange={e=>{onFile(e.target.files[0]);e.target.value='';}}/></div>;
}

function PartyForm({value, onChange, seller=false}) {
  const fields=[['name',seller?'Nombre del emisor':'Nombre del cliente'],['street','Dirección'],['postcode','Código postal'],['city','Ciudad'],['country','País (ISO)'],['email','Email'],['phone','Teléfono'],['vat_id','USt-IdNr.'],['tax_number','Steuernummer'],[seller?'iban':'buyer_reference',seller?'IBAN':'Referencia del comprador']];
  return <div className="form-grid">{fields.map(([key,label])=><Field label={label} key={key} className={['name','street'].includes(key)?'span-2':''}><input value={value[key] || ''} onChange={e=>onChange({...value,[key]:key==='country'?e.target.value.toUpperCase():e.target.value})} required={key==='name'} type={key==='email'?'email':'text'} maxLength={key==='country'?2:180}/></Field>)}</div>;
}

function RecordEditor({initial, boot, busy, onSave, onUpload, onContact}) {
  const source=initial.data || initial;
  const invoice=initial.kind==='invoice';
  const imported=Boolean(initial.source);
  const [kind,setKind]=useState(initial.kind);
  const [client,setClient]=useState(source.party_id || '');
  const [party,setParty]=useState(source.party_name || '');
  const [dateValue,setDate]=useState(source.date || today());
  const [serviceDate,setService]=useState(source.service_date || today());
  const [due,setDue]=useState(source.due_date || plusDays(today(),14));
  const [reference,setReference]=useState(source.reference || '');
  const [buyerReference,setBuyerReference]=useState(source.buyer_reference || '');
  const [note,setNote]=useState(source.note || '');
  const [reason,setReason]=useState(source.exemption_reason || '');
  const [life,setLife]=useState(source.asset_life_months || '');
  const [assetStart,setAssetStart]=useState(source.asset_start || today());
  const [docs,setDocs]=useState(initial.documents || []);
  const [lines,setLines]=useState(source.lines?.map(x=>({...x,base:inputAmount(x.net_cents),tax:inputAmount(x.tax_cents)})) || [{description:'',activity:'freiberufler',base:'0,00',tax:'0,00',tax_code:'de19',category:invoice?'other':'software',deduct_percent:100}]);
  const [localError,setLocalError]=useState('');
  const [newClient,setNewClient]=useState(false);
  const [clientDraft,setClientDraft]=useState({...EMPTY_PARTY});
  const uploadInput=useRef(null);
  function updateLine(index, patch) {setLines(rows=>rows.map((line,i)=>i===index?{...line,...patch}:line));}
  function calculated(line) {let base=0,tax=0;try {base=parseAmount(line.base);const rate={de19:19,de7:7,de0:0}[line.tax_code];tax=imported||rate===undefined?parseAmount(line.tax):Math.round(base*rate/100);} catch {} return {base,tax};}
  const sum=lines.reduce((total,line)=>{const {base,tax}=calculated(line);return total+base+tax;},0);
  const taxCodes=Object.entries(boot.tax_codes).filter(([key])=>(invoice || kind==='income') ? ['de19','de7','de0','exempt','rc_income_eu','rc_income_de','rc_income_other','unclassified'].includes(key) : !key.startsWith('rc_income'));
  async function save(e) {
    e.preventDefault();setLocalError('');
    try {
      const payload={kind,date:dateValue,service_date:serviceDate,due_date:invoice?due:null,party_id:imported?source.party_id:invoice?client:null,party_name:party,reference,buyer_reference:buyerReference,note,exemption_reason:reason,
        lines:lines.map(line=>{const base=parseAmount(line.base);const rate={de19:19,de7:7,de0:0}[line.tax_code];const tax=imported||rate===undefined?parseAmount(line.tax):Math.round(base*rate/100);return {description:line.description,activity:line.activity,net_cents:base,tax_cents:tax,tax_code:line.tax_code,category:['tax_payment','tax_refund'].includes(kind)?kind==='tax_payment'?'vat_payment':'vat_refund':line.category,deduct_percent:Number(line.deduct_percent)};}),
        document_ids:docs.filter(doc=>!doc.role||doc.role==='original').map(doc=>doc.id),asset_life_months:kind==='asset'?Number(life):null,asset_start:kind==='asset'?assetStart:null,revision:initial.revision || null};
      await onSave(payload);
    } catch(e) {setLocalError(e.message);}
  }
  return <form className="record-form" onSubmit={save}>
    <Notice error>{localError}</Notice>
    {imported ? <Notice>Los importes, fechas, justificantes y centro de coste se actualizan desde sevdesk.</Notice> : null}
    {source.source_unsupported ? <Notice error>{source.source_unsupported} El original se conserva.</Notice> : null}
    {invoice ? <Field label="Cliente"><div className="client-select"><select disabled={imported} required value={client} onChange={e=>{if(e.target.value==='new'){setNewClient(true);}else{setClient(e.target.value);setNewClient(false);}}}><option value="">Seleccionar cliente</option>{boot.contacts.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}<option value="new">+ Nuevo cliente</option></select></div></Field> : <div className="form-grid"><Field label={['income','tax_refund'].includes(kind)?'Pagador':'Proveedor'}><input disabled={imported} required value={party} onChange={e=>setParty(e.target.value)}/></Field><Field label="Tipo de gasto"><select value={kind} onChange={e=>{setKind(e.target.value);if(e.target.value.startsWith('tax_'))setLines(ls=>ls.map(l=>({...l,tax_code:'none',tax:'0,00'})));}} disabled={initial.state==='reviewed'}><option value="expense">Gasto</option><option value="income">Ingreso · justificante</option><option value="asset">Activo · amortización</option><option value="tax_payment">Pago de IVA al Finanzamt</option><option value="tax_refund">Devolución de IVA del Finanzamt</option></select></Field></div>}
    {newClient ? <div className="inline-form"><h2>Nuevo cliente</h2><PartyForm value={clientDraft} onChange={setClientDraft}/><button type="button" className="secondary" disabled={busy} onClick={async()=>{const result=await onContact(clientDraft);if(result){setClient(result.id);setNewClient(false);}}}>Guardar cliente</button></div> : null}
    <Field label="Actividad"><select disabled={imported&&Boolean(source.source_cost_centre_id)} value={lines[0].activity} onChange={e=>updateLine(0,{activity:e.target.value})}>{Object.entries(boot.activities).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field>
    <div className="form-grid"><Field label="Fecha"><input disabled={imported} type="date" required value={dateValue} onChange={e=>setDate(e.target.value)}/></Field><Field label={invoice?'Vencimiento':'Fecha de prestación'}><input disabled={imported} type="date" required value={invoice?due:serviceDate} onChange={e=>invoice?setDue(e.target.value):setService(e.target.value)}/></Field></div>
    {lines.map((line,index)=><div className="line-editor" key={index}>
      {index>0 ? <div className="line-heading"><strong>Concepto {index+1}</strong><button disabled={imported} type="button" className="text-button" onClick={()=>setLines(ls=>ls.filter((_,i)=>i!==index))}>Quitar</button></div> : null}
      {index>0 ? <Field label="Actividad"><select disabled={imported&&Boolean(source.source_cost_centre_id)} value={line.activity} onChange={e=>updateLine(index,{activity:e.target.value})}>{Object.entries(boot.activities).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field> : null}
      <Field label="Concepto"><textarea disabled={imported} required rows={3} value={line.description} onChange={e=>updateLine(index,{description:e.target.value})} placeholder={invoice?'Leistung beschreiben':'Beschreibung des Belegs'}/></Field>
      <div className="form-grid amount-pair"><Field label="Base (€)"><input disabled={imported} required inputMode="decimal" value={line.base} onChange={e=>updateLine(index,{base:e.target.value})}/></Field><Field label="IVA"><select value={line.tax_code} onChange={e=>updateLine(index,{tax_code:e.target.value,tax:imported||['de19','de7','foreign','unclassified'].includes(e.target.value)?line.tax:'0,00'})}>{taxCodes.map(([key,label])=><option key={key} value={key}>{key==='de19'?'19 %':key==='de7'?'7 %':key==='de0'?'0 %':label}</option>)}</select></Field></div>
      {['foreign','unclassified'].includes(line.tax_code) ? <Field label="IVA del justificante (€)"><input disabled={imported} inputMode="decimal" value={line.tax} onChange={e=>updateLine(index,{tax:e.target.value})}/></Field> : null}
      {!invoice ? <div className="form-grid"><Field label="Categoría"><select value={line.category} onChange={e=>updateLine(index,{category:e.target.value})}>{Object.entries(boot.categories).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field><Field label="Deducción profesional (%)"><input type="number" min="0" max="100" value={line.deduct_percent} onChange={e=>updateLine(index,{deduct_percent:e.target.value})}/></Field></div> : null}
    </div>)}
    <div className="form-total"><strong>Total</strong><strong>{euro(sum)}</strong></div>
    <button disabled={imported} type="button" className="text-button add-line" onClick={()=>setLines(ls=>[...ls,{...ls[0],description:'',base:'0,00',tax:'0,00'}])}>+ Añadir concepto / reparto</button>
    <details className="extra-fields"><summary>{invoice?'Prestación, referencia y notas':'Justificante, referencia y notas'}</summary>
      {invoice ? <><Field label="Fecha de prestación"><input disabled={imported} type="date" required value={serviceDate} onChange={e=>setService(e.target.value)}/></Field><Field label="Referencia del comprador"><input disabled={imported} value={buyerReference} onChange={e=>setBuyerReference(e.target.value)} placeholder="Referencia acordada o Leitweg-ID"/></Field></> : <>
      <Field label="Número del justificante"><input disabled={imported} value={reference} onChange={e=>setReference(e.target.value)}/></Field><button type="button" className="secondary" disabled={busy||imported} onClick={()=>uploadInput.current.click()}>Añadir justificante</button><input type="file" ref={uploadInput} className="visually-hidden" accept=".pdf,.xml,.png,.jpg,.jpeg" onChange={async e=>{const file=e.target.files[0];if(file){const result=await onUpload(file);if(result)setDocs(ds=>[...ds,result]);}e.target.value='';}}/>
      </>}
      <Field label="Notas"><textarea rows={2} value={note} onChange={e=>setNote(e.target.value)}/></Field>
      {lines.some(line=>line.tax_code==='exempt') ? <Field label="Fundamento de la exención"><input required value={reason} onChange={e=>setReason(e.target.value)}/></Field> : null}
    </details>
    {docs.length ? <div className="document-list">{docs.filter(d=>d.role!=='source_json').map(doc=><a key={doc.id} href={'/api/documents/'+doc.id} target="_blank" rel="noreferrer">{doc.filename}</a>)}</div> : null}
    {kind==='asset' ? <div className="form-grid"><Field label="Puesta en uso"><input type="date" required value={assetStart} onChange={e=>setAssetStart(e.target.value)}/></Field><Field label="Vida útil verificada (meses)"><input type="number" required min="1" max="1200" value={life} onChange={e=>setLife(e.target.value)}/></Field></div> : null}
    <button className="primary save-button" type="submit" disabled={busy}>{busy?'Guardando…':'Guardar borrador'}</button>
  </form>;
}

function RecordDetail({row, boot, onClose, onEdit, act, busy, onChanged}) {
  const sheet=useRef(null);
  useEffect(()=>{const previous=document.activeElement;sheet.current?.querySelector('button')?.focus();return()=>{if(previous?.isConnected)previous.focus();};},[]);
  const [preview,setPreview]=useState(null);
  const [cash,setCash]=useState(false);
  const [cashAmount,setCashAmount]=useState(inputAmount(Math.max(0,row.total-row.paid)));
  const [cashDate,setCashDate]=useState(today());
  const [error,setError]=useState('');
  async function run(fn, message) {const result=await act(fn,message);if(result){setPreview(null);await onChanged();}return result;}
  return <div className="sheet-backdrop" onClick={onClose}><section ref={sheet} className="detail-sheet" role="dialog" aria-modal="true" aria-labelledby="detail-title" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();onClose();}if(e.key==='Tab'){const controls=[...sheet.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')];const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}}><div className="sheet-heading"><h2 id="detail-title">{row.number || row.data.reference || (row.kind==='invoice'?'Borrador de factura':'Justificante')}</h2><button className="icon-button" aria-label="Cerrar detalle" onClick={onClose}><Icon name="close"/></button></div>
    <p>{displayDate(row.date)} · {STATUS[row.state]}{row.source?' · sevdesk':''}</p><p className="detail-total">{euro(row.total)}</p><p>Pagado: {euro(row.paid)} · Pendiente: {euro(row.total-row.paid)}</p>
    {row.data.lines.map((line,i)=><div key={i} className="detail-line"><strong>{line.description}</strong><span>{row.state==='private'||activityPending(row)?activityLabel(row,boot.activities):boot.activities[line.activity]} · {boot.tax_codes[line.tax_code]}</span><span>{euro(line.net_cents)} + {euro(line.tax_cents)}</span></div>)}
    <div className="document-list">{row.documents?.map(doc=><a key={doc.id+doc.role} href={'/api/documents/'+doc.id} target="_blank" rel="noreferrer">{doc.filename}</a>)}</div>
    <Notice error>{error}</Notice>
    {row.data.source_unsupported ? <Notice error>{row.data.source_unsupported}</Notice> : null}
    {row.data.source_sync_error ? <Notice error>{row.data.source_sync_error}</Notice> : null}
    {['draft','needs_review'].includes(row.state) ? <div className="actions"><button className="secondary" disabled={busy} onClick={onEdit}>Editar clasificación</button>{row.kind==='invoice'&&!row.source ? <button className="primary" disabled={busy} onClick={async()=>{try{setPreview(await api('records/'+row.id+'/invoice-preview'));setError('');}catch(e){setError(e.message);}}}>Revisar XRechnung</button> : <button className="primary" disabled={busy} onClick={()=>run(()=>api('records/'+row.id+'/review',{method:'POST',body:{revision:row.revision}}),'Documento cerrado y clasificado.')}>Confirmar revisión</button>}</div> : null}
    {preview ? <div className="inline-form"><h3>{preview.snapshot.number}</h3><p>Cliente: {preview.snapshot.buyer.name}</p><p>{preview.validator}: válida.</p><p>Al emitir se fija el número y se conserva el PDF y XML. La factura queda pendiente de pago.</p><button className="primary" disabled={busy} onClick={()=>run(()=>api('records/'+row.id+'/issue',{method:'POST',body:{sha256:preview.sha256,confirm:true}}),'Factura emitida. PDF y XML guardados.')}>Emitir factura · {euro(row.total)}</button></div> : null}
    {!row.source&&['issued','reviewed'].includes(row.state)&&row.paid<row.total ? <div className="cash-section"><button className="text-button" onClick={()=>setCash(!cash)}>Registrar pago fuera del extracto</button>{cash ? <form onSubmit={async e=>{e.preventDefault();try{await run(()=>api('records/'+row.id+'/payments',{method:'POST',body:{date:cashDate,amount:parseAmount(cashAmount)}}),'Pago registrado.');setCash(false);}catch(e){setError(e.message);}}}><Field label="Fecha efectiva del pago"><input type="date" value={cashDate} onChange={e=>setCashDate(e.target.value)} required/></Field><Field label="Importe (€)"><input inputMode="decimal" value={cashAmount} onChange={e=>setCashAmount(e.target.value)} required/></Field><button className="secondary" disabled={busy}>Registrar pago</button></form> : null}</div> : null}
    {row.payments?.length ? <><h3>Pagos</h3>{row.payments.map(payment=><div className="payment-row" key={payment.id}><span>{displayDate(payment.date)} · {euro(payment.amount)}{payment.reversed_by?' · Revertido':''}</span>{!row.source&&!payment.reversed_by ? <button className="text-button" disabled={busy} onClick={()=>run(()=>api('payments/'+payment.id+'/reverse',{method:'POST'}),'Pago revertido; el original permanece en el historial.')}>Revertir</button> : null}</div>)}</> : null}
    {row.state==='draft'&&!row.source ? <button className="text-button discard" disabled={busy} onClick={async()=>{const result=await act(()=>api('records/'+row.id+'/void',{method:'POST',body:{revision:row.revision}}),'Borrador descartado.');if(result)onClose();}}>Descartar borrador</button> : null}
  </section></div>;
}

function BankPage({boot, rows, act, busy}) {
  const [account,setAccount]=useState(boot.accounts[0]?.id || '');
  const [accountName,setAccountName]=useState('');
  const [selection,setSelection]=useState(null);
  const [candidates,setCandidates]=useState([]);
  const [recordId,setRecordId]=useState('');
  const [amount,setAmount]=useState('0,00');
  const [reason,setReason]=useState('');
  const [error,setError]=useState('');
  const [filter,setFilter]=useState('pending');
  const file=useRef(null);
  const visible=rows.filter(row=>filter==='all'||row.classification==='unreviewed'&&row.matched<Math.abs(row.amount));
  async function choose(row) {setSelection(row);setReason('');setRecordId('');setAmount(inputAmount(Math.abs(row.amount)-row.matched));try {const records=await api('records?start=2000-01-01&end=2099-12-31');setCandidates(records.filter(rec=>['issued','reviewed'].includes(rec.state)&&rec.paid<rec.total&&((row.amount>0)===['invoice','income','tax_refund'].includes(rec.kind))));} catch(e){setError(e.message);}}
  return <>
    <div className="bank-toolbar"><Field label="Cuenta"><select value={account} onChange={e=>setAccount(e.target.value)}><option value="">Seleccionar cuenta</option>{boot.accounts.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></Field><button className="secondary" disabled={!account||busy} onClick={()=>file.current.click()}>Importar CSV / CAMT</button><input className="visually-hidden" type="file" ref={file} accept=".csv,.xml" onChange={async e=>{const selected=e.target.files[0];if(selected){const form=new FormData();form.append('account_id',account);form.append('file',selected);await act(()=>api('bank/import',{method:'POST',body:form}),'Extracto importado.');}e.target.value='';}}/><Field label="Mostrar"><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="pending">Pendientes</option><option value="all">Todos</option></select></Field></div>
    {!boot.accounts.length ? <form className="inline-form" onSubmit={async e=>{e.preventDefault();const value=await act(()=>api('bank/accounts',{method:'POST',body:{name:accountName}}),'Cuenta creada.');if(value)setAccount(value.id);}}><Field label="Nombre de la cuenta"><input required value={accountName} onChange={e=>setAccountName(e.target.value)}/></Field><button className="secondary" disabled={busy}>Crear cuenta EUR</button></form> : <details className="extra-fields"><summary>Añadir cuenta y formato del CSV</summary><form className="bank-toolbar" onSubmit={async e=>{e.preventDefault();const value=await act(()=>api('bank/accounts',{method:'POST',body:{name:accountName}}),'Cuenta creada.');if(value)setAccount(value.id);}}><Field label="Nombre de la cuenta"><input required value={accountName} onChange={e=>setAccountName(e.target.value)}/></Field><button className="secondary" disabled={busy}>Crear cuenta EUR</button></form><p>CSV UTF-8: date;amount;party;purpose;reference. Fecha AAAA-MM-DD o DD.MM.AAAA. Importe negativo para salidas. CAMT: movimientos contabilizados en EUR. Si un extracto solapa el histórico de sevdesk, revisa posibles duplicados antes de declarar.</p></details>}
    <div className="table-wrap"><table><thead><tr><th>Fecha</th><th>Nombre / Concepto</th><th>Cuenta</th><th className="amount">Importe</th><th>Estado</th><th/></tr></thead><tbody>{visible.length ? visible.map(row=><tr key={row.id}><td>{displayDate(row.date)}</td><td><strong>{row.party || 'Movimiento'}</strong><span className="cell-subtext">{row.purpose}</span></td><td>{row.account}</td><td className="amount strong">{euro(row.amount)}</td><td>{row.matched===Math.abs(row.amount)?'Conciliado':row.classification==='private'?(row.matched?'Parcial + privado':'Privado'):row.classification==='transfer'?(row.matched?'Parcial + traslado':'Traslado'):row.classification==='excluded'?(row.matched?'Parcial + excluido':'Excluido'):row.matched?'Parcial':'Pendiente'}</td><td><button className="table-link" onClick={()=>choose(row)}>Revisar</button></td></tr>) : <Empty columns={6} title="No hay movimientos pendientes." description="Importa un extracto o consulta todos los movimientos."/>}</tbody></table></div>
    {selection ? <div className="inline-form"><div className="line-heading"><h2>Conciliar movimiento</h2><button className="text-button" onClick={()=>setSelection(null)}>Cerrar</button></div><p>{displayDate(selection.date)} · {selection.party} · {euro(selection.amount)} · Disponible: {euro(Math.abs(selection.amount)-selection.matched)}</p><Notice error>{error}</Notice><form className="form-grid" onSubmit={async e=>{e.preventDefault();try{const result=await act(()=>api('bank/'+selection.id+'/match',{method:'POST',body:{record_id:recordId,amount:parseAmount(amount)}}),'Movimiento conciliado.');if(result)setSelection(null);}catch(e){setError(e.message);}}}><Field label="Documento"><select required value={recordId} onChange={e=>{setRecordId(e.target.value);const rec=candidates.find(x=>x.id===e.target.value);if(rec)setAmount(inputAmount(Math.min(rec.total-rec.paid,Math.abs(selection.amount)-selection.matched)));}}><option value="">Seleccionar documento revisado</option>{candidates.map(rec=><option key={rec.id} value={rec.id}>{rec.number||rec.data.reference||rec.data.party_name} · {euro(rec.total-rec.paid)}</option>)}</select></Field><Field label="Importe a conciliar (€)"><input inputMode="decimal" required value={amount} onChange={e=>setAmount(e.target.value)}/></Field><button className="primary" disabled={busy||!recordId}>Conciliar importe</button></form><div className="classification"><Field label={selection.matched?"Motivo para el resto sin conciliar":"Motivo de clasificación"}><input value={reason} onChange={e=>setReason(e.target.value)} placeholder="Privado, traslado entre cuentas o duplicado verificado"/></Field><div className="actions">{[['private','Marcar privado'],['transfer','Traslado'],['excluded','Excluir con motivo'],['unreviewed','Volver a pendiente']].map(([key,label])=><button className="secondary" key={key} disabled={busy||reason.length<4} onClick={async()=>{const result=await act(()=>api('bank/'+selection.id+'/classify',{method:'POST',body:{classification:key,reason}}),'Clasificación guardada.');if(result)setSelection(null);}}>{label}</button>)}</div></div></div> : null}
  </>;
}

function ReportPage({type, act, boot}) {
  const [period,setPeriod]=useState(type==='eur'?'2026':'2026-10');
  const [report,setReport]=useState(null);
  const [error,setError]=useState('');
  const [closeNotes,setCloseNotes]=useState('');
  useEffect(()=>{let active=true;setReport(null);api('reports/'+(type==='eur'?'eur/':'vat/')+period).then(r=>{if(active){setReport(r);setError('');}}).catch(e=>active&&setError(e.message));return()=>{active=false;};},[period,type]);
  const labels={revenue_net:'Betriebseinnahmen ohne USt',vat_received:'Vereinnahmte Umsatzsteuer',vat_refunds:'Umsatzsteuererstattungen',expenses:'Betriebsausgaben ohne abziehbare USt',input_vat_paid:'Gezahlte Vorsteuer',vat_paid:'Umsatzsteuer an das Finanzamt',depreciation:'AfA · amortización',income_total:'Total ingresos',expense_total:'Total gastos',profit:'Beneficio'};
  async function prepare(activity) {await act(()=>api('returns/prepare',{method:'POST',body:{type:type==='eur'?'eur':'ustva',period,activity:activity||null}}),'Declaración guardada para revisión. No enviada a ELSTER.');}
  return <><div className="filters"><Field label={type==='eur'?'Año':'Mes'}><input type={type==='eur'?'number':'month'} value={period} min={type==='eur'?'2026':'2026-01'} max={type==='eur'?'2099':'2099-12'} onChange={e=>setPeriod(e.target.value)}/></Field></div><Notice error>{error}</Notice>{report ? <>
    <p className="report-basis">{type==='eur'?'Una EÜR anual por actividad · criterio de cobros y pagos':'UStVA mensual · ambas actividades'} · {report.ready?'Preparada':'Borrador'}</p><Blockers items={report.blockers}/>
    {type==='eur' ? <>{report.activities.map(item=><section key={item.activity} className="report-section"><h2>{item.name}</h2><table className="report-table"><tbody>{Object.entries(labels).map(([key,label])=><tr key={key} className={key==='profit'?'profit':''}><th>{label}</th><td className="amount">{euro(item.values[key]||0)}</td></tr>)}</tbody></table><div className="actions"><a className="secondary button-link" href={'/api/exports/eur/'+period+'/'+item.activity}>Descargar EÜR CSV</a><button className="primary" disabled={!report.ready} onClick={()=>prepare(item.activity)}>Preparar esta EÜR</button></div></section>)}<details className="extra-fields"><summary>Revisión de cierre anual</summary><p>Confirma al terminar el año los activos iniciales, gastos pendientes y la imputación de pagos recurrentes alrededor del cambio de año (§ 11 EStG). Cualquier cambio contable posterior vuelve a exigir revisión.</p><Field label="Notas de la revisión anual"><textarea value={closeNotes} onChange={e=>setCloseNotes(e.target.value)} rows={3}/></Field><button className="secondary" disabled={closeNotes.length<10} onClick={async()=>{const value=await act(()=>api('reports/eur/'+period+'/close',{method:'POST',body:{sha256:report.fingerprint,confirm:true,notes:closeNotes}}),'Cierre anual revisado.');if(value)setReport(value);}}>Confirmar cierre anual</button></details></> : <><table className="report-table"><thead><tr><th>Kennziffer</th><th>Concepto</th><th className="amount">EUR</th></tr></thead><tbody>{Object.entries(report.fields).map(([key,value])=><tr key={key}><td>{key}</td><th>{report.labels[key]}</th><td className="amount">{new Intl.NumberFormat('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value))}</td></tr>)}<tr className="profit"><td/><th>Resultado mensual · a pagar / devolver</th><td className="amount">{euro(report.payable_cents)}</td></tr></tbody></table><div className="actions"><a className="secondary button-link" href={'/api/exports/vat/'+period}>Descargar revisión</a><button className="primary" disabled={!report.ready} onClick={()=>prepare()}>Preparar UStVA</button></div></>}
    <section className="elster-section"><h2>ELSTER</h2><p>{boot.elster.message}</p><button className="secondary" disabled>Enviar a ELSTER · pendiente de activar</button><a className="text-link" href={boot.elster.registration_url} target="_blank" rel="noreferrer">Registro de desarrollador en ELSTER</a></section>
  </> : !error ? <p>Cargando declaración…</p> : null}</>;
}

function Settings({boot, act, busy}) {
  const [seller,setSeller]=useState({...EMPTY_PARTY,...boot.settings.seller});
  const [method,setMethod]=useState(boot.settings.vat_method);
  const [prefix,setPrefix]=useState(boot.settings.number_prefix);
  const [next,setNext]=useState(boot.settings.next_number);
  const [confirmed,setConfirmed]=useState(boot.settings.fiscal_reviewed);
  const [audit,setAudit]=useState(null);
  const [contact,setContact]=useState(null);
  const [registration,setRegistration]=useState(null);
  return <><form className="settings-form" onSubmit={e=>{e.preventDefault();act(()=>api('settings',{method:'PUT',body:{seller,vat_method:method,number_prefix:prefix,next_number:Number(next),fiscal_reviewed:confirmed}}),'Configuración guardada.');}}><h2>Emisor</h2><PartyForm value={seller} onChange={setSeller} seller/><h2>Fiscalidad y numeración</h2><div className="form-grid"><Field label="Método de IVA"><select value={method} onChange={e=>setMethod(e.target.value)}><option value="unconfirmed">Pendiente de confirmar</option><option value="ist">Ist-Versteuerung · según cobro</option><option value="soll">Soll-Versteuerung · según prestación</option></select></Field><Field label="Prefijo de factura"><input value={prefix} onChange={e=>setPrefix(e.target.value)} placeholder="BL-{year}-"/></Field><Field label="Siguiente número"><input type="number" min="1" value={next} onChange={e=>setNext(e.target.value)}/></Field></div><label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>He revisado la identidad del emisor, Steuernummer y método fiscal.</span></label><button className="primary" disabled={busy}>Guardar configuración</button></form>
    <section className="settings-section"><h2>Clientes</h2>{boot.contacts.length ? <div className="contacts-list">{boot.contacts.map(c=><button key={c.id} className="table-link" onClick={()=>setContact(c)}>{c.name}</button>)}</div> : <p>No hay clientes todavía.</p>}{contact ? <form className="inline-form" onSubmit={async e=>{e.preventDefault();const {id,...party}=contact;const result=await act(()=>api('contacts/'+id,{method:'PUT',body:party}),'Cliente actualizado.');if(result)setContact(null);}}><PartyForm value={contact} onChange={setContact}/><div className="actions"><button className="secondary" type="button" onClick={()=>setContact(null)}>Cerrar</button><button className="primary" disabled={busy}>Guardar cliente</button></div></form> : null}</section>
    <section className="settings-section"><h2>Histórico 2026</h2><p><ImportStatus value={boot.import}/></p>{boot.import.summary ? <><p>{Object.entries(boot.import.summary.counts || {}).map(([key,value])=>key+': '+value).join(' · ')}</p><Blockers items={[...(boot.import.summary.errors || []),...(boot.import.summary.source_drift || [])]}/></> : null}<p>El importador utiliza sevdesk solo en lectura. Los documentos originales permanecen cifrados en el NUC.</p></section>
    <section className="settings-section"><h2>Envío a ELSTER</h2><p>{boot.elster.message}</p><div className="actions"><button className="secondary" onClick={async()=>{const value=await act(()=>api('elster/registration-draft'),'Solicitud preparada para revisar. No enviada.');if(value)setRegistration(value);}}>Ver solicitud de acceso a ERiC</button><a className="text-link" href={boot.elster.source_url} target="_blank" rel="noreferrer">Requisitos oficiales de ERiC</a></div>{registration ? <div className="inline-form"><h3>Solicitud de desarrollador · sin enviar</h3><p>{registration.name} · {registration.company}</p><p>{registration.email} · {registration.phone} · {registration.website}</p><p>{registration.reason}</p><a href={registration.url} target="_blank" rel="noreferrer" className="secondary button-link">Abrir registro oficial</a></div> : null}</section>
    <section className="settings-section"><h2>Historial</h2><button className="secondary" onClick={async()=>{try{setAudit(await api('audit'));}catch(e){await act(()=>Promise.reject(e));}}}>Comprobar integridad</button>{audit ? <><p>{audit.verification.events} eventos · cadena verificada.</p><div className="table-wrap"><table><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th></tr></thead><tbody>{audit.events.map(event=><tr key={event.seq}><td>{new Date(event.at).toLocaleString('es-ES')}</td><td>{event.actor}</td><td>{event.event}</td></tr>)}</tbody></table></div></> : null}</section>
  </>;
}

createRoot(document.getElementById('root')).render(<App/>);
