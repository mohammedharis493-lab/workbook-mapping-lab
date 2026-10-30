/* Local browser interface. No network requests leave 127.0.0.1. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name=local-token]').content;
let state = {config:{}, entries:[], fields:[], warnings:[], issues:[], unresolved:[], latest_saved:null};
let selectedSource = '', selectedWarning = -1, visibleTab = 'sources';
const sourceKeys = [
 ['source','Current-year financial statements'],
 ['previous','Previous-year financial statements'],
 ['profile','Reviewed FS extraction profile (.json)'],
 ['layout','Approved destination layout (.csv)'],
 ['prior_rules','Approved prior-year mapping rules (.csv)'],
 ['previous_target','Completed previous-year Winman export'],
 ['detail_routes','Detailed field definitions (.csv)'],
 ['advisory_rules','Optional evidence warning checks (.json)'],
 ['folder','Private working folder']
];
const benchmarkKeys = [
 ['benchmark_generated','Previously generated import-format workbook'],
 ['completed_reference','Independently completed ITR workbook (.xlsm / .xlsx)'],
 ['benchmark_contract','Approved field comparison contract (.csv)']
];
const buildKeys = [
 ['template','Original current-year Winman template'],
 ['source_controls','Financial statement control totals'],
 ['output_controls','Expected return control totals'],
 ['companion_details','Approved parent/detail allocations (.csv)'],
 ['output','New output filename (not the original)']
];
let toastTime = null;

function notice(message, error=false) {
 const el=$('toast'); el.textContent=message; el.className='show'+(error?' error':'');
 window.clearTimeout(toastTime); toastTime=window.setTimeout(()=>{el.className='';},6500);
}
async function api(path, payload={}, method='POST') {
 const res=await fetch(path, {
  method,
  headers:{'X-Session-Token':token,'Content-Type':'application/json'},
  ...(method==='POST'?{body:JSON.stringify(payload)}:{})
 });
 let parsed;try{parsed=await res.json();}catch{throw new Error('Unexpected local response');}
 if(!res.ok || parsed.ok===false) throw new Error(parsed.error||'Local request was rejected');
 return method==='GET'?parsed:parsed.data;
}
function node(tag, text='', cls='') {
 const el=document.createElement(tag);
 if(text!==null)el.textContent=String(text);
 if(cls)el.className=cls;
 return el;
}
function fieldInputs(holder, pairs) {
 pairs.forEach(([key,label])=>{
  const wrap=node('label');
  wrap.textContent=label;
  const input=node('input'); input.type='text';input.id='file-'+key;
  input.dataset.pathKey=key;input.spellcheck=false;input.autocomplete='off';
  input.placeholder=key==='folder'?'C:\\private\\...':'Path to a local file';
  input.addEventListener('change',()=>input.dataset.changed='yes');
  wrap.append(input);holder.append(wrap);
 });
}
fieldInputs($('source-inputs'),sourceKeys.filter(([key])=>['source','previous','previous_target'].includes(key)));
fieldInputs($('source-advanced-inputs'),sourceKeys.filter(([key])=>!['source','previous','previous_target'].includes(key)));
fieldInputs($('build-inputs'),buildKeys.filter(([key])=>['template','output'].includes(key)));
fieldInputs($('build-advanced-inputs'),buildKeys.filter(([key])=>!['template','output'].includes(key)));
fieldInputs($('benchmark-inputs'),benchmarkKeys);
function collectPaths() {
 const updates={};
 document.querySelectorAll('input[data-path-key]').forEach(el=>{
  if(el.value.trim()!==String(state.config[el.dataset.pathKey]||''))
    updates[el.dataset.pathKey]=el.value.trim();
 });
 return updates;
}
async function syncPaths() {
 const updates=collectPaths();
 if(Object.keys(updates).length){const result=await api('/api/config',updates);state=result;}
}
function showTab(id) {
 visibleTab=id;
 document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!=='view-'+id);
 document.querySelectorAll('.tab').forEach(el=>{
  const active=el.dataset.view===id;
  el.classList.toggle('active',active);
  if(active)el.setAttribute('aria-current','page');
  else el.removeAttribute('aria-current');
 });
}
document.querySelectorAll('.tab').forEach(el=>el.addEventListener('click',()=>showTab(el.dataset.view)));
$('footer-help').addEventListener('click',()=>$('help-dialog').showModal());
document.addEventListener('pointerdown',event=>{
 const menu=$('view-menu');
 if(menu.open && !menu.contains(event.target))menu.open=false;
});

function cell(row, value, cls='') {const td=node('td',value,cls);row.append(td);return td;}
function emptyRow(table,message,cols) {
 const tr=document.createElement('tr');const td=cell(tr,message,'empty');td.colSpan=cols;table.tBodies[0].append(tr);
}
function renderFindings() {
 const tb=$('findings-table').tBodies[0];tb.replaceChildren();
 $('findings-summary').textContent=state.issues.length?(state.issues.length+' findings'):'No findings';
 if(state.issues.length && $('findings-panel') && visibleTab==='sources')$('findings-panel').open=true;
 if(!state.issues.length) {emptyRow($('findings-table'),'No extraction findings.',3);return;}
 state.issues.forEach(w=>{
  const tr=tb.insertRow();
  cell(tr,w.issue||w.code||'Notice');
  cell(tr,w.source_id||'General');
  cell(tr,w.detail||'');
 });
}
function renderPaths() {
 document.querySelectorAll('input[data-path-key]').forEach(el=>{
  const val=state.config[el.dataset.pathKey]||'';
  if(document.activeElement!==el) el.value=val;
 });
}
function renderMapping() {
 const entries=state.entries||[];
 const open=state.unresolved||[];
 $('unresolved-count').textContent=String(open.length);
 $('status-mini').textContent=entries.length?entries.length+' extracted items':'No review started';
 $('metric-extracted').textContent=String(entries.length);
 $('metric-approved').textContent=String(entries.length-open.length);
 $('metric-pending').textContent=String(open.length);
 const tbody=$('mapping-table').tBodies[0];tbody.replaceChildren();
 const q=$('mapping-search').value.toLowerCase().trim();
 const visible=entries.filter(e=>!q||[
   e.caption,e.source_id,e.section,e.target_hint,e.risk
 ].some(x=>String(x||'').toLowerCase().includes(q)));
 if(!visible.length){emptyRow($('mapping-table'),entries.length?'No matching rows.':'Extract sources first.',5);}
 visible.forEach(entry=>{
  const tr=tbody.insertRow();
  tr.dataset.id=entry.source_id;tr.tabIndex=0;
  if(entry.source_id===selectedSource)tr.classList.add('selected');
  const itemCell=cell(tr,entry.caption||entry.source_id,'item');
  itemCell.append(node('small',entry.section+' · '+entry.source_id));
  cell(tr,entry.amount||'0','number');
  cell(tr,entry.previous_amount||'—','number');
  cell(tr,entry.target_hint||'—');
  const status=cell(tr,'');
  status.append(node('span',entry.review_status||'Needs review',
    'pill '+String(entry.review_status||'needs_review').toLowerCase()));
  tr.addEventListener('click',()=>selectSource(entry.source_id));
  tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectSource(entry.source_id);}});
 });
 const exists=entries.some(e=>e.source_id===selectedSource);
 if(!exists)selectedSource='';
 if(selectedSource)fillDecision();
 else {
  $('selected-source').textContent='Choose a row to review';
  $('selected-risk').textContent='The item\'s supporting details and any exceptions will appear here.';
 }
}
function selectSource(id) {
 selectedSource=id;fillDecision();
 document.querySelectorAll('#mapping-table tr[data-id]').forEach(tr=>tr.classList.toggle('selected',tr.dataset.id===id));
}
function fillDecision() {
 const item=state.entries.find(e=>e.source_id===selectedSource);if(!item)return;
 $('selected-source').textContent=item.caption||item.source_id;
 $('selected-risk').textContent=(item.section+' · '+item.source_id+'\n')+
   (item.risk||item.notice||'No additional source risk recorded.');
 const select=$('destination');
 const old=select.value;select.replaceChildren();
 select.append(node('option','Select destination'));
 select.firstChild.value='';
 state.fields.filter(f=>f.section===item.section).forEach(field=>{
  const option=node('option',field.field_id+' · '+(field.anchor_text||field.sheet));
  option.value=field.field_id;select.append(option);
 });
 const value=item.target_hint&&select.querySelector('option[value="'+CSS.escape(item.target_hint)+'"]')?item.target_hint:old;
 select.value=[...select.options].some(x=>x.value===value)?value:'';
 $('approve-risk').checked=false;
}
function warningKey(item){return [item.code,item.period,item.title].join('|');}
function renderWarnings(){
 const warnings=state.warnings||[];
 $('warning-count').textContent=String(warnings.filter(x=>x.severity==='Review').length);
 const list=$('warning-list');list.replaceChildren();
 if(!warnings.length){list.append(node('p','No advisory findings for the supplied evidence.','muted'));}
 warnings.forEach((item,index)=>{
  const b=node('button',null,'warning-card'+(selectedWarning===index?' active':''));
  b.type='button';
  b.append(node('span',item.severity,'pill '+item.severity.toLowerCase()));
  b.append(node('strong',item.title));
  b.append(node('small',item.period+(item.difference?' · Difference '+item.difference:'')+
    (item.acknowledged?' · Reviewed':'')));
  b.addEventListener('click',()=>selectWarning(index));list.append(b);
 });
 if(selectedWarning>=warnings.length)selectedWarning=-1;
 if(selectedWarning>=0)showWarningDetail(warnings[selectedWarning]);
}
function selectWarning(index){selectedWarning=index;renderWarnings();}
function showWarningDetail(w) {
 $('warning-title').textContent=w.title;
 $('warning-explanation').textContent=w.explanation;
 $('warning-note').value=w.reviewer_note||'';
 const evidence=$('warning-evidence');evidence.replaceChildren();
 w.evidence.forEach(e=>{
  const div=node('div',null,'evidence-line');
  const label=node('div');label.append(node('strong',e.description||'Evidence'));
  label.append(node('div',(e.source||'')+' · '+(e.sheet||'')+'!'+(e.cell||''),'muted'));
  div.append(label,node('strong',e.amount||e.text||''));
  evidence.append(div);
 });
 const action=$('warning-action');action.replaceChildren();
 action.append(node('p','Suggested check: '+w.suggested_action,'notice'));
}
function renderGateStatus(){
 const el=$('build-gate-status');
 const open=(state.unresolved||[]).length;
 const missing=(state.issues||[]).filter(x=>x.issue==='VENDOR_TEMPLATE_DETAIL_MISSING').length;
 const other=(state.issues||[]).filter(x=>x.issue!=='VENDOR_TEMPLATE_DETAIL_MISSING').length;
 let text='';
 if(!state.entries.length){text='Start by extracting the financial statements under Sources.';}
 else if(missing){text=missing+' required Winman detail schedule'+(missing===1?' is':'s are')+' missing. '+open+' mapping decision'+(open===1?'':'s')+' remain. A complete official export is needed.';}
 else if(open || other){text=open+' mapping decision'+(open===1?'':'s')+' remain; '+other+' source finding'+(other===1?'':'s')+' require review.';}
 else{text='Mappings reviewed. Save the review, then run the checked build.';}
 el.textContent=text;
 el.classList.toggle('ready',!open&&!missing&&!other&&state.entries.length>0);
}
function renderBenchmark(){
 const record=state.latest_benchmark;
 const body=$('benchmark-table').tBodies[0];body.replaceChildren();
 if(!record){$('benchmark-summary').textContent='No comparison run.';
  emptyRow($('benchmark-table'),'Run comparison to see results.',5);return;}
 $('benchmark-summary').textContent=record.fully_matched+' of '+record.contract_fields+' reviewed fields matched; '+
   record.unavailable_targets+' required native targets unavailable. Private report: '+record.private_report;
 record.details.forEach(item=>{
  const tr=body.insertRow();
  cell(tr,item.field_id);
  cell(tr,item.fs_expected,'number');
  cell(tr,item.generated?.amount||item.generated?.state||'Unavailable','number');
  cell(tr,item.manual?.amount||item.manual?.state||'Unavailable','number');
  const td=cell(tr,'');
  td.append(node('span',item.status==='MATCH'?'Match':item.checks.join(', '),
    'pill '+(item.status==='MATCH'?'approved':'needs_review')));
 });
}
function renderTemplatePreflight(){
 const current=state.latest_preflight;
 const status=$('template-readiness-status');
 const list=$('template-readiness-list');
 list.replaceChildren();
 if(!current){
  status.textContent='Not checked in this session.';
  return;
 }
 status.textContent=current.status+' · '+current.current_sheet_count+
  ' current worksheets · '+current.detail_fields_resolved+
  '/'+current.detail_fields_requested+' configured detail fields located. '+current.next_step;
 (current.missing_sheets||[]).forEach(sheet=>{
  list.append(node('li','Missing native detail worksheet: '+sheet));
 });
 (current.field_issues||[]).forEach(issue=>{
  list.append(node('li','Field '+(issue.field_id||'')+': '+issue.code));
 });
}
function render(){
 renderPaths();renderMapping();renderFindings();renderWarnings();renderGateStatus();renderBenchmark();renderTemplatePreflight();
}
async function run(task,msg) {
 try{
  document.body.classList.add('working');
  $('main').setAttribute('aria-busy','true');
  await task();
  if(msg)notice(msg);
 }catch(error){notice(error.message||String(error),true);}
 finally{document.body.classList.remove('working');$('main').removeAttribute('aria-busy');}
}
$('mapping-search').addEventListener('input',renderMapping);
$('save-paths').addEventListener('click',()=>run(async()=>{
 await syncPaths();render();},'Local paths updated for this session.'));
$('template-readiness-run').addEventListener('click',()=>run(async()=>{
 await syncPaths();
 state=await api('/api/template-readiness');
 render();
 $('template-diagnostics').open=true;
 },'Read-only official export inspection completed.'));
$('extract').addEventListener('click',()=>run(async()=>{
 await syncPaths();state=await api('/api/extract');selectedSource='';selectedWarning=-1;render();
 showTab('mapping');},'Source extraction completed. Review all suggested classifications.'));
$('warnings-refresh').addEventListener('click',()=>run(async()=>{
 await syncPaths();state=await api('/api/warnings');render();
 },'Evidence warnings refreshed; no mappings changed.'));
$('approve').addEventListener('click',()=>run(async()=>{
 if(!selectedSource)throw new Error('Choose a source row first');
 if(!$('destination').value)throw new Error('Choose a destination field');
 state=await api('/api/approve',{source_id:selectedSource,field_id:$('destination').value,
 portion:$('portion').value,sign:$('sign').value,
 acknowledge_risks:$('approve-risk').checked});
 render();},'The selected mapping has been approved.'));
$('revoke').addEventListener('click',()=>run(async()=>{
 if(!selectedSource)throw new Error('Choose a source row first');
 state=await api('/api/revoke',{source_id:selectedSource});render();
 },'Mapping approval revoked.'));
$('warning-reviewed').addEventListener('click',()=>warningAction(true));
$('warning-reopen').addEventListener('click',()=>warningAction(false));
function warningAction(acknowledged){run(async()=>{
 if(selectedWarning<0)throw new Error('Select a warning first');
 state=await api('/api/warning-decision',{
  index:selectedWarning,acknowledged,note:$('warning-note').value
 });render();},'Advisory updated; no financial data changed.');}
$('warnings-export').addEventListener('click',()=>run(async()=>{
 await syncPaths();const data=await api('/api/warnings-export');
 notice('Private warning report saved: '+data.path);
}));
$('review-export').addEventListener('click',()=>run(async()=>{
 await syncPaths();const data=await api('/api/save-review');
 state=data;
 $('build-result').textContent='Review '+data.result.status+' · '+data.result.report;
 render();
 },'Private review exported. Check any blocking exceptions.'));
$('resolve-btn').addEventListener('click',()=>run(async()=>{
 await syncPaths();state=await api('/api/resolve-details');
 render();},'Official detailed fields resolved; review the new layout.'));
$('benchmark-run').addEventListener('click',()=>run(async()=>{
 await syncPaths();state=await api('/api/benchmark-completed');render();
 $('benchmark-section').open=true;
 },'Completed-return comparison saved privately. Examine the individual field results.'));
$('build-copy').addEventListener('click',()=>run(async()=>{
 await syncPaths();
 if(!window.confirm('Build a separate, new local Excel file? The original template will not be overwritten.'))return;
 const data=await api('/api/build');
 state=data;
 $('build-result').textContent='Status: '+data.result.status+
  ' · Check report: '+data.report+
  (data.result.output_path?' · Workbook: '+data.result.output_path:'');
 render();
 if(data.result.status!=='PASS')throw new Error('Build blocked by structural or reconciliation checks. See private report.');
 },'Checked copy generated and verified.'));
$('scan-btn').addEventListener('click',()=>run(async()=>{
 await syncPaths();
 const sheet=window.prompt('Worksheet name for a read-only scan:','Sch VI-BS');
 if(!sheet)return;
 const data=await api('/api/scan',{sheet,first:1,last:350});
 const rows=data.rows||[];
 const tbody=$('findings-table').tBodies[0];tbody.replaceChildren();
 rows.forEach(x=>{const tr=tbody.insertRow();
  cell(tr,x.row);cell(tr,x.caption);cell(tr,x.current_amount+' · '+(x.risk||''));});
 if(!rows.length)emptyRow($('findings-table'),'No numeric rows found.',3);
 showTab('sources');
 notice('Read-only scan found '+rows.length+' candidates. Use reviewed FS profile to include new sources.');
}));
window.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&document.querySelector('dialog[open]'))document.querySelector('dialog[open]').close();
});
(async()=>{
 try{state=await api('/api/state',{},'GET');render();showTab('sources');}
 catch(err){notice('Local server is not reachable: '+err.message,true);}
})();
})();
