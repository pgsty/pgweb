// 消息翻译 (/nls/): PostgreSQL 19 zh_CN 消息校准表。
// 通过 /nls/api/* 读写。所有人可浏览；保存需要 nls.review 权限，bootstrap 返回权限后页面切为只读或可编辑。
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const h=escapeHTML;
const labels={pending:'待审',approved:'已校对',flagged:'标疑',rejected:'否定',stale:'需重审'};
const kindLabels={retained:'保留措辞',format:'调整格式',revised:'修订语义',new:'补充新译'};
const kindTitles={retained:'保留措辞：推荐沿用现有译法',format:'调整格式：只改标点、空格或占位符写法',revised:'修订语义：含义或措辞有变化',new:'补充新译：原本没有译文'};
const refKinds={approved:'人工通过',human:'人工稿',candidate:'当前候选'};
const svg=d=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+d+'</svg>';
const ICON={
 chevron:svg('<path d="M6 9l6 6 6-6"/>'),
 history:svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>'),
 user:svg('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>')
};
const STATUS_ICON={
 approved:svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4 12 14.01l-3-3"/>'),
 pending:svg('<circle cx="12" cy="12" r="9"/>'),
 flagged:svg('<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>'),
 rejected:svg('<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>'),
 stale:svg('<path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>'),
 dirty:svg('<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>'),
 failed:svg('<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>')
};
const KIND_ICON={
 retained:svg('<path d="M5 9h14M5 15h14"/>'),
 format:svg('<path d="M4 7V4h16v3M9 20h6M12 4v16"/>'),
 revised:svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>'),
 new:svg('<circle cx="12" cy="12" r="10"/><path d="M12 8v8M8 12h8"/>')
};
function matchesFilter(r,filter='all'){
 switch(filter){
  case 'all':return true;
  case 'dirty':return !!r._dirty;
  case 'approved':return r.status==='approved';
  case 'pending':return r.status==='pending'||r.status==='stale';
  case 'issue':return r.status==='flagged'||r.status==='rejected';
  case 'human':return r.version>0;
  case 'second_pass':return !!r.calibration?.previous_changed;
  default:return filter.startsWith('cal:')?r.calibration?.kind===filter.slice(4):r.old_assessment===filter;
 }
}
function visibleRecords(records,{query='',filter='all'}={}){
 const q=query.toLowerCase().trim();
 return records.filter(r=>(!q||[r.english,r.english_plural,...Object.values(r.original_forms),...Object.values(r.forms),...Object.values(r.suggested_forms||{})].join('\n').toLowerCase().includes(q))&&matchesFilter(r,filter));
}
function hasSeparateRecommendation(r){
 return r.version>0&&r.suggested_forms&&Object.keys(r.suggested_forms).some(k=>r.forms[k]!==r.suggested_forms[k]);
}
const TOKEN=/%(?:\d+\$)?[-+#0 ']*(?:\*|\d+)?(?:\.(?:\*|\d+))?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspnm%]/g;
const placeholders=s=>(String(s??'').match(TOKEN)||[]).filter(t=>t!=='%%').map(t=>t.replace(/^%\d+\$/,'%')).sort();
function placeholderMismatch(english,translation){
 const a=placeholders(english),b=placeholders(translation);
 return a.length!==b.length||a.some((t,i)=>t!==b[i]);
}
// 现有翻译单元格的背景档位：相对当前校准译文。
function oldCellKind(r){
 const keys=Object.keys(r.forms);
 if(!keys.some(k=>r.original_forms[k]))return 'none';
 if(!r.english_plural&&keys.some(k=>r.original_forms[k]&&placeholderMismatch(r.english,r.original_forms[k])))return 'severe';
 return keys.every(k=>(r.original_forms[k]??'')===(r.forms[k]??''))?'same':'differs';
}
// 逐字差异：equal / delete / insert / replace 片段，两侧文本都能原样重建。
function charDiff(a,b){
 const A=Array.from(String(a??'')),B=Array.from(String(b??''));
 if(!A.length&&!B.length)return [];
 let start=0;const max=Math.min(A.length,B.length);
 while(start<max&&A[start]===B[start])start++;
 let end=0;
 while(end<max-start&&A[A.length-1-end]===B[B.length-1-end])end++;
 const ops=[];
 if(start){const s=A.slice(0,start).join('');ops.push({op:'equal',a:s,b:s})}
 ops.push(...middleDiff(A.slice(start,A.length-end),B.slice(start,B.length-end)));
 if(end){const s=A.slice(A.length-end).join('');ops.push({op:'equal',a:s,b:s})}
 return ops;
}
function middleDiff(A,B){
 const n=A.length,m=B.length;
 if(!n&&!m)return [];
 if(!n)return [{op:'insert',a:'',b:B.join('')}];
 if(!m)return [{op:'delete',a:A.join(''),b:''}];
 if(n*m>400000)return [{op:'replace',a:A.join(''),b:B.join('')}];
 const W=m+1,L=new Uint32Array((n+1)*W);
 for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i*W+j]=A[i]===B[j]?L[(i+1)*W+j+1]+1:Math.max(L[(i+1)*W+j],L[i*W+j+1]);
 const segs=[];const push=(op,a,b)=>{const last=segs[segs.length-1];if(last&&last.op===op){last.a+=a;last.b+=b}else segs.push({op,a,b})};
 let i=0,j=0;
 while(i<n&&j<m){
  if(A[i]===B[j]){push('equal',A[i],B[j]);i++;j++}
  else if(L[(i+1)*W+j]>=L[i*W+j+1]){push('delete',A[i],'');i++}
  else{push('insert','',B[j]);j++}
 }
 while(i<n)push('delete',A[i++],'');
 while(j<m)push('insert','',B[j++]);
 for(let k=1;k<segs.length-1;k++)if(segs[k].op==='equal'&&Array.from(segs[k].a).length<=1&&segs[k-1].op!=='equal'&&segs[k+1].op!=='equal')segs[k].op='replace';
 const out=[];
 for(let k=0;k<segs.length;){
  if(segs[k].op==='equal'){out.push(segs[k]);k++;continue}
  let a='',b='';
  while(k<segs.length&&segs[k].op!=='equal'){a+=segs[k].a;b+=segs[k].b;k++}
  out.push({op:a&&b?'replace':a?'delete':'insert',a,b});
 }
 return out;
}
const visible=t=>h(t).replace(/ /g,'<span class="ws" title="空格">·</span>').replace(/\t/g,'<span class="ws" title="制表符">⇥</span>').replace(/\n/g,'<span class="ws" title="换行">↵</span>\n');
function sideMarkup(ops,side){
 return ops.map(o=>{
  const t=side==='a'?o.a:o.b;
  if(!t)return '';
  if(o.op==='equal')return text(t);
  return '<span class="'+(o.op==='replace'?'d-chg':side==='a'?'d-del':'d-ins')+'">'+visible(t)+'</span>';
 }).join('');
}
function diffMarkup(parts,tag){
 return parts.map(p=>p.changed?'<'+tag+'>'+visible(p.text)+'</'+tag+'>':h(p.text)).join('');
}
function decisionFor(r,status='pending'){
 return {id:r.id,expected_version:r.version,status,forms:{...r.forms},note:r.note};
}
function applySave(r,result,serial){
 r.version=result.version;r.status=result.status;r.stored_status=result.stored_status;r.updated_at=result.updated_at;r.reviewer=result.reviewer||'';
 r._dirty=r._serial!==serial;
 if(!r._dirty){r.forms={...result.forms};r.note=result.note}
 r._saved={status:result.stored_status,forms:{...result.forms},note:result.note};
 return r;
}
const text=v=>h(v).replace(/(%(?:\d+\$)?[-+#0 ']*(?:\*|\d+)?(?:\.(?:\*|\d+))?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspnm%]|%&lt;PRI[^;]+;)/g,'<span class="format-token">$1</span>');

const root=document.getElementById('nls');
if(root)void start(root);
async function start(root){
 const $=id=>document.getElementById('nls-'+id);
 const state={components:[],records:[],byId:new Map(),component:'',query:'',filter:'all',busy:false,undo:[],lastSaved:null,activeId:null,user:{authenticated:false,can_edit:false,login_url:root.dataset.login}};
 const canEdit=()=>state.user.can_edit;
 let toastTimer,searchTimer;
 const local={get:k=>{try{return localStorage.getItem(k)}catch{return null}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch{}},del:k=>{try{localStorage.removeItem(k)}catch{}}};
 const n=v=>Number(v).toLocaleString('zh-CN');
 const isFull=()=>root.classList.contains('fullscreen');
 const scroller=()=>isFull()?root:window;
 async function api(path,body){
  const response=await fetch('/nls/api/'+path,body===undefined?{headers:{'Accept':'application/json'}}:{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRFToken':root.dataset.csrf},body:JSON.stringify(body)});
  let value=null;
  try{value=await response.json()}catch{value={error:'请求失败（HTTP '+response.status+'）'}}
  if(!response.ok){const e=new Error(value.error||'请求失败（HTTP '+response.status+'）');e.status=response.status;e.login=value.login_url;throw e}
  return value;
 }
 function toast(message,failed=false,html=''){const el=$('toast');if(html)el.innerHTML=html;else el.textContent=message.length>180?message.slice(0,180)+'…':message;el.classList.toggle('failed',failed);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,failed?5000:2500)}
 function error(e){
  const message=e.message||String(e);
  $('error').textContent=/Failed to fetch|Load failed/.test(message)?'无法连接服务器。未保存的文字仍保留在页面上，恢复后请再次保存。':message;
  $('error').hidden=false;refreshStatus();
  if($('submit-dialog').open){$('submit-error').textContent=$('error').textContent;$('submit-error').hidden=false}
  if(e.status===401)toast('',true,'登录后才能保存 — <a href="'+h(e.login||state.user.login_url)+'">登录</a>');
 }
 function setBusy(b){
  state.busy=b;root.classList.toggle('busy',b);
  root.querySelectorAll('.nls-toolbar button,.nls-toolbar select,.nls-tools input,.nls-tools select,.nls-dialog button').forEach(el=>el.disabled=b);
  refreshStatus();
 }
 function refreshStatus(){
  const dirty=state.records.filter(r=>r._dirty).length,saving=state.records.some(r=>r._saving);
  $('save-state').textContent=!canEdit()?'':saving?'正在保存…':dirty?dirty+' 行尚未保存':state.lastSaved?'已保存 '+state.lastSaved.slice(11,19):'';
  $('save-state').classList.toggle('dirty',dirty>0);
  $('save-component').disabled=state.busy||!dirty;
  $('submit-component').disabled=state.busy||!state.records.length;
  $('undo').disabled=state.busy||!state.undo.length;
 }
 function renderUser(){
  const u=state.user;
  $('user').innerHTML=u.can_edit?'<span class="who">'+h(u.name)+'</span> · 审校人':u.authenticated?'<span class="who">'+h(u.name)+'</span> · 只读':'只读 · <a href="'+h(u.login_url)+'">登录</a>后可校对';
  for(const id of ['undo','save-component','submit-component','export'])$(id).hidden=!u.can_edit;
  const notice=$('notice');
  if(u.can_edit){notice.hidden=true}
  else{notice.hidden=false;notice.innerHTML=u.authenticated?'当前账号没有 <code>nls.review</code> 校对权限，表格为只读；请联系管理员授权。':'当前为只读模式，<a href="'+h(u.login_url)+'">登录</a>审校账号后可勾选、编辑与保存；浏览、搜索和键盘导航无需登录。'}
 }
 function renderSidebar(){
  const query=$('component-search').value.toLowerCase();
  $('components').innerHTML=state.components.filter(c=>c.name.includes(query)).map(c=>'<button type="button" class="component-button'+(c.name===state.component?' active':'')+'" data-component="'+h(c.name)+'" title="已校对 '+c.approved+' / '+c.total+'"><span class="name">'+h(c.name)+'</span><span class="count">'+c.approved+'<i>/</i>'+c.total+'</span></button>').join('');
  $('component-select').innerHTML=state.components.map(c=>'<option value="'+h(c.name)+'"'+(c.name===state.component?' selected':'')+'>'+h(c.name)+'  '+c.approved+'/'+c.total+'</option>').join('');
 }
 function progress(){
  const c=state.components.find(c=>c.name===state.component);
  if(c){c.approved=state.records.filter(r=>r.status==='approved').length;$('component-summary').textContent=n(state.records.length)+' 条 · 已校对 '+n(c.approved)+' 条'}
  renderSidebar();refreshStatus();
 }
 // ---- 行渲染 ----
 const rowDiffs=r=>Object.fromEntries(Object.keys(r.forms).map(k=>[k,charDiff(r.original_forms[k]??'',r.forms[k]??'')]));
 const formLabel=k=>k!==''?'<span class="form-label">形式 '+h(k)+'</span>':'';
 function oldCellHTML(r,diffs){
  return Object.keys(r.forms).map((k,i)=>(i?'<div class="form-separator">':'<div>')+formLabel(k)+((r.original_forms[k]??'')?sideMarkup(diffs[k],'a'):'<span class="none" title="原本缺译">—</span>')+'</div>').join('');
 }
 function editableHTML(r,k,index,diff){
  const edit=canEdit()?' role="textbox" tabindex="0" title="点击或按 Enter 编辑"':'';
  return '<div class="editable'+(canEdit()?'':' readonly')+'"'+edit+' aria-label="第 '+(index+1)+' 行译文'+(k!==''?' 形式 '+k:'')+'" data-edit="'+h(k)+'">'+formLabel(k)+((r.original_forms[k]??'')?sideMarkup(diff,'b'):text(r.forms[k]))+'</div>';
 }
 const candidateCellHTML=(r,index,diffs)=>Object.keys(r.forms).map(k=>editableHTML(r,k,index,diffs[k])).join('');
 function statusHTML(r){
  const [cls,label,title]=r._error?['failed','保存失败',r._error]:r._dirty?['dirty','未保存','尚未保存']:[r.status,labels[r.status]||r.status,labels[r.status]||r.status];
  const pill='<span class="pill '+h(cls)+(r._saving?' saving':'')+'" title="'+h(title)+'">'+(STATUS_ICON[cls]||'')+'<span>'+h(label)+'</span></span>';
  const tags=[];const k=r.calibration?.kind;
  if(k)tags.push('<span class="tag '+h(k)+'" title="'+h(kindTitles[k]||r.calibration.label||k)+'">'+(KIND_ICON[k]||'')+'</span>');
  if(r.calibration?.previous_changed)tags.push('<span class="tag second" title="推荐译文与上一轮不同">'+ICON.history+'</span>');
  if(r.version>0)tags.push('<span class="tag human" title="'+h('人工稿'+(r.reviewer?' · 最后保存：'+r.reviewer:''))+'">'+ICON.user+'</span>');
  const open=!!$('details-'+r.id);
  return pill+tags.join('')+'<button type="button" class="icon row-expand'+(open?' open':'')+'" data-expand aria-expanded="'+open+'" title="展开详情（→）" aria-label="展开本行">'+ICON.chevron+'</button>';
 }
 function rowHTML(r,index){
  const diffs=rowDiffs(r);
  return '<tr class="message-row'+(r.id===state.activeId?' active':'')+'" id="nls-row-'+r.id+'" data-id="'+r.id+'"><td class="check-cell"><input type="checkbox" data-check aria-label="第 '+(index+1)+' 行已校对"'+(r.status==='approved'?' checked':'')+(canEdit()?'':' class="ro" aria-disabled="true" title="登录审校账号后才能勾选"')+'></td><td class="english"><span class="row-num">'+(index+1)+'</span>'+text(r.english)+(r.english_plural?'<div class="form-separator"><span class="form-label">复数原文</span>'+text(r.english_plural)+'</div>':'')+'</td><td class="old '+oldCellKind(r)+'" lang="zh-CN">'+oldCellHTML(r,diffs)+'</td><td class="candidate'+(r._error?' failed':'')+'" lang="zh-CN">'+candidateCellHTML(r,index,diffs)+'</td><td class="status-cell"><div class="status">'+statusHTML(r)+'</div></td></tr>';
 }
 function renderTable(){
  const records=visibleRecords(state.records,state);
  $('rows').innerHTML=records.length?records.map(r=>rowHTML(r,r._index)).join(''):'<tr><td colspan="5" class="empty">没有匹配的记录</td></tr>';
  $('table-end').textContent='显示 '+n(records.length)+' / '+n(state.records.length)+' 条消息';
  progress();
 }
 const rowEl=id=>$('row-'+id);
 function paintOld(row,r,diffs){const old=row.querySelector('.old');old.className='old '+oldCellKind(r);old.innerHTML=oldCellHTML(r,diffs)}
 function refreshRow(r){
  const row=rowEl(r.id);if(!row)return;
  row.querySelector('.status').innerHTML=statusHTML(r);
  row.querySelector('[data-check]').checked=r.status==='approved';
  row.querySelector('.old').className='old '+oldCellKind(r);
  row.querySelector('.candidate').classList.toggle('failed',!!r._error);
 }
 function renderCells(r){
  const row=rowEl(r.id);if(!row)return;
  const diffs=rowDiffs(r);paintOld(row,r,diffs);
  row.querySelector('.candidate').innerHTML=candidateCellHTML(r,r._index,diffs);
 }
 // ---- 列宽：三列文本列可拖动，宽度以占比记住；状态列记像素 ----
 const table=root.querySelector('.nls-table');
 const cols={check:root.querySelector('col.check-col'),text:[root.querySelector('col.english-col'),root.querySelector('col.old-col'),root.querySelector('col.new-col')],status:root.querySelector('col.status-col')};
 const DEFAULT_FRACTIONS=[0.40,0.30,0.30],DEFAULT_STATUS=196,MIN_TEXT=80,MIN_STATUS=150,MAX_STATUS=320;
 let fractions=(()=>{try{const v=JSON.parse(local.get('pgnls-col-fractions')||'null');return Array.isArray(v)&&v.length===3&&Math.abs(v.reduce((a,b)=>a+b,0)-1)<0.01?v:DEFAULT_FRACTIONS.slice()}catch{return DEFAULT_FRACTIONS.slice()}})();
 let statusWidth=Math.min(MAX_STATUS,Math.max(MIN_STATUS,+local.get('pgnls-status-width')||DEFAULT_STATUS));
 const headerCells=()=>[...table.querySelectorAll('thead th')];
 function applyWidths(){
  if(window.innerWidth<768){for(const c of [...cols.text,cols.status])c.style.width='';return}
  const checkW=headerCells()[0].getBoundingClientRect().width||36;
  const avail=table.parentElement.clientWidth-checkW-statusWidth;
  if(avail<3*MIN_TEXT)return;
  const px=fractions.map(f=>Math.max(MIN_TEXT,Math.round(avail*f)));
  px[2]=Math.max(MIN_TEXT,avail-px[0]-px[1]);
  cols.text.forEach((c,i)=>c.style.width=px[i]+'px');cols.status.style.width=statusWidth+'px';
 }
 function saveWidths(){local.set('pgnls-col-fractions',JSON.stringify(fractions.map(f=>+f.toFixed(4))));local.set('pgnls-status-width',String(statusWidth))}
 root.querySelectorAll('.col-grip').forEach(grip=>{
  grip.addEventListener('pointerdown',e=>{
   if(e.button!==0)return;
   e.preventDefault();const i=+grip.dataset.grip;
   const widths=headerCells().slice(1,4).map(th=>th.getBoundingClientRect().width),startX=e.clientX,startStatus=statusWidth;
   grip.classList.add('dragging');root.classList.add('resizing');try{grip.setPointerCapture(e.pointerId)}catch{}
   const move=ev=>{
    const delta=ev.clientX-startX;
    if(i<2){const a=Math.min(Math.max(MIN_TEXT,widths[i]+delta),widths[i]+widths[i+1]-MIN_TEXT),b=widths[i]+widths[i+1]-a;const w=widths.slice();w[i]=a;w[i+1]=b;cols.text.forEach((c,k)=>c.style.width=Math.round(w[k])+'px')}
    else{const st=Math.min(MAX_STATUS,Math.max(MIN_STATUS,startStatus-delta));const a=widths[2]+(startStatus-st);cols.text[2].style.width=Math.round(a)+'px';cols.status.style.width=Math.round(st)+'px'}
   };
   const up=()=>{
    window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',up);
    grip.classList.remove('dragging');root.classList.remove('resizing');
    const cells=headerCells(),now=cells.slice(1,4).map(th=>th.getBoundingClientRect().width),sum=now.reduce((a,b)=>a+b,0);
    fractions=now.map(w=>w/sum);statusWidth=Math.min(MAX_STATUS,Math.max(MIN_STATUS,Math.round(cells[4].getBoundingClientRect().width)));saveWidths();applyWidths();
   };
   window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);window.addEventListener('pointercancel',up);
  });
  grip.addEventListener('dblclick',()=>{fractions=DEFAULT_FRACTIONS.slice();statusWidth=DEFAULT_STATUS;local.del('pgnls-col-fractions');local.del('pgnls-status-width');applyWidths();toast('列宽已恢复默认')});
  grip.addEventListener('click',e=>e.stopPropagation());
 });
 let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(applyWidths,80)});
 // ---- 全屏：#nls 铺满视口，隐藏站点页头页脚与组件侧栏，表格拿到整页宽度 ----
 function setFullscreen(on){
  root.classList.toggle('fullscreen',on);document.body.classList.toggle('nls-fullscreen',on);
  $('fullscreen').setAttribute('aria-pressed',String(on));$('fullscreen').title=on?'退出全屏（Esc）':'全屏（Esc 退出）';
  if(on)root.scrollTop=0;
  requestAnimationFrame(applyWidths);
 }
 $('fullscreen').onclick=()=>setFullscreen(!isFull());
 $('component-select').hidden=false;
 $('component-select').onchange=()=>{const name=$('component-select').value;if(name&&name!==state.component)void run(async()=>{await flush();await loadComponent(name)})};
 // ---- 当前行与键盘 ----
 const rowCheckbox=id=>rowEl(id)?.querySelector('[data-check]');
 function setActive(id){
  if(state.activeId===id)return;
  rowEl(state.activeId)?.classList.remove('active');state.activeId=id;rowEl(id)?.classList.add('active');
 }
 function ensureVisible(row){
  const box=row.getBoundingClientRect(),head=root.querySelector('thead').getBoundingClientRect().bottom;
  if(box.top<head)scroller().scrollBy(0,box.top-head-6);
  else if(box.bottom>window.innerHeight)scroller().scrollBy(0,box.bottom-window.innerHeight+12);
 }
 function focusRow(id,scroll=true){
  const cb=rowCheckbox(id);if(!cb)return;
  setActive(id);cb.focus({preventScroll:true});if(scroll)ensureVisible(cb.closest('tr'));
 }
 function siblingRow(row,dir){let el=row;do el=dir>0?el.nextElementSibling:el.previousElementSibling;while(el&&!el.classList.contains('message-row'));return el}
 // ---- 保存（撤销栈在浏览器端：撤销 = 把上一状态再保存一次） ----
 function rowError(r,e){r._error=e.message||String(e);refreshRow(r);error(e);if(e.status!==401)toast(r._error,true)}
 function markDirty(r){
  r._serial++;r._dirty=true;r._error='';clearTimeout(r._timer);
  refreshRow(r);refreshStatus();
  r._timer=setTimeout(()=>{if(!state.busy&&!r._composing)void saveRow(r).catch(e=>rowError(r,e))},650);
 }
 async function saveRow(r,status='pending',remember=false){
  clearTimeout(r._timer);
  while(r._saving)await r._saving;
  if(!r._dirty&&(!remember||r.stored_status===status))return;
  r._saving=(async()=>{
   do{
    const serial=r._serial,before=r._saved,result=await api('decide/',decisionFor(r,status));
    applySave(r,result,serial);r._error='';state.lastSaved=result.updated_at;
    if(remember)state.undo.push({items:[{id:r.id,before,expected:result.version}]});
   }while(r._dirty&&status==='pending');
  })().finally(()=>{r._saving=null;refreshRow(r);progress()});
  refreshRow(r);refreshStatus();return r._saving;
 }
 async function rowAction(r,fn){
  if(state.busy){toast('正在执行其他操作，请稍候');refreshRow(r);return}
  $('error').hidden=true;
  try{await fn()}catch(e){rowError(r,e)}finally{refreshRow(r);progress()}
 }
 const setStatus=(r,status)=>rowAction(r,()=>saveRow(r,status,true));
 async function flush(){
  for(const r of state.records)clearTimeout(r._timer);
  await Promise.all(state.records.map(r=>r._saving).filter(Boolean));
  for(const r of state.records)if(r._dirty)await saveRow(r);
 }
 async function run(fn){
  if(state.busy)return;
  $('error').hidden=true;setBusy(true);
  try{await fn()}catch(e){error(e)}finally{setBusy(false)}
 }
 async function bootstrap(){
  const data=await api('bootstrap/');
  state.components=data.components;state.lastSaved=data.storage.last_saved;state.user=data.user;
  $('overall').textContent=n(data.total)+' 条消息 · '+n(data.forms)+' 个译文形式';
  $('component-count').textContent=data.components.length;
  renderUser();renderSidebar();
  return data;
 }
 async function loadComponent(name){
  const data=await api('component/?name='+encodeURIComponent(name));
  state.component=name;state.activeId=null;
  state.records=data.records.map((r,index)=>({...r,forms:{...r.forms},_index:index,_dirty:false,_serial:0,_saving:null,_error:'',_saved:{status:r.stored_status,forms:{...r.forms},note:r.note}}));
  state.byId=new Map(state.records.map(r=>[r.id,r]));state.query='';state.filter='all';
  $('search').value='';$('filter').value='all';$('component-title').textContent=name;
  renderTable();applyWidths();local.set('pgnls-table-component',name);scroller().scrollTo(0,0);
 }
 function editCell(el,r){
  if(state.busy||!canEdit()||!el||el.tagName==='TEXTAREA')return;
  const form=el.dataset.edit,area=document.createElement('textarea');
  area.dataset.edit=form;area.setAttribute('aria-label',el.getAttribute('aria-label'));area.value=r.forms[form];area.lang='zh-CN';
  area.rows=Math.max(1,Math.min(18,area.value.split('\n').length));el.replaceWith(area);area.focus();
  area.setSelectionRange(area.value.length,area.value.length);
 }
 function adoptRecommendation(r){
  if(state.busy||!canEdit())return;
  r.forms={...r.suggested_forms};renderCells(r);markDirty(r);toast('已采用二次推荐');
  $('details-'+r.id)?.querySelector('.recommendation')?.remove();
 }
 async function undo(){
  const action=state.undo.at(-1);if(!action)return;
  await flush();
  if(action.items.length===1){
   const item=action.items[0],r=state.byId.get(item.id);
   const result=await api('decide/',{id:item.id,expected_version:item.expected,...item.before});
   if(r){applySave(r,result,r._serial);refreshRow(r)}
  }else{
   const result=await api('save/',{component:state.component,decisions:action.items.map(i=>({id:i.id,expected_version:i.expected,...i.before}))});
   for(const value of result.results){const r=state.byId.get(value.id);if(r){applySave(r,value,r._serial);refreshRow(r)}}
  }
  state.undo.pop();progress();toast('上次操作已撤销');
 }
 // ---- 详情 ----
 function referenceHTML(ref){
  const sources=[...new Set(ref.sources.map(s=>s.component+(s.reviewer?' · '+s.reviewer:'')))];
  const en=ref.diff.map(d=>d.changed?'<mark>'+text(d.text)+'</mark>':text(d.text)).join('');
  return '<article class="reference"><div class="reference-head"><b class="'+(ref.kind==='approved'?'human':'')+'">'+h(refKinds[ref.kind]||ref.kind)+'</b><span>'+(ref.exact?'英文相同':'相似 '+Math.round(ref.similarity*100)+'%')+'</span><span>'+h(sources.slice(0,3).join(' / '))+'</span></div><div class="reference-pair"><div>'+en+(ref.english_plural?'<br>复数：'+text(ref.english_plural):'')+'</div><div lang="zh-CN">'+text(ref.translation)+'</div></div></article>';
 }
 function diffHTML(title,rows){
  return '<div class="calibration-diff"><div class="detail-heading">'+h(title)+' <span class="nls-muted">红色删除 · 绿色新增 · “·” 表示空格</span></div>'+rows.map(r=>'<div class="diff-pair">'+(r.form!==''?'<div class="form-label">形式 '+h(r.form)+'</div>':'')+'<div><label>之前</label><pre lang="zh-CN">'+diffMarkup(r.before,'del')+'</pre></div><div><label>二次推荐</label><pre lang="zh-CN">'+diffMarkup(r.after,'ins')+'</pre></div></div>').join('')+'</div>';
 }
 function recommendationHTML(r){
  const pairs=Object.keys(r.suggested_forms).map(k=>{const ops=charDiff(r.forms[k]??'',r.suggested_forms[k]??'');return '<div class="diff-pair">'+(k!==''?'<div class="form-label">形式 '+h(k)+'</div>':'')+'<div><label>当前人工稿</label><pre lang="zh-CN">'+sideMarkup(ops,'a')+'</pre></div><div><label>二次推荐</label><pre lang="zh-CN">'+sideMarkup(ops,'b')+'</pre></div></div>'}).join('');
  return '<div class="recommendation"><div class="detail-heading">二次推荐与当前人工稿不同 <span class="nls-muted">表格中显示的是人工稿</span><span class="nls-spacer"></span>'+(canEdit()?'<button type="button" class="nls-btn nls-quiet" data-adopt>采用推荐</button>':'')+'</div>'+pairs+'</div>';
 }
 function savedInfo(r){
  if(!(r.version>0))return '尚无人工修改';
  return '最后保存：'+(r.reviewer?h(r.reviewer)+' · ':'')+(r.updated_at?h(r.updated_at)+' · ':'')+'v'+r.version;
 }
 function detailsHTML(r,data){
  const ro=canEdit()?'':' disabled';
  return '<div class="row-details"><div class="detail-top"><div><label>校准说明</label><p>'+h(r.assessment_reason)+'</p><label>语境、参数与源码位置</label><p>'+h([data.context.context,data.context.parameters,data.context.locations].filter(Boolean).join('\n'))+'</p>'+(r.plural_issue?'<p class="nls-error">'+h(r.plural_issue)+'</p>':'')+'</div><div><label for="nls-note-'+r.id+'">备注</label><textarea id="nls-note-'+r.id+'" data-note placeholder="疑问、依据或给其他审校人的说明…"'+ro+'></textarea><div class="detail-row"><label>人工状态</label><select data-status aria-label="本行人工状态"'+ro+'>'+Object.entries(labels).filter(([key])=>key!=='stale').map(([key,label])=>'<option value="'+key+'" '+(r.stored_status===key?'selected':'')+'>'+label+'</option>').join('')+'</select><span class="nls-muted">'+savedInfo(r)+'</span></div></div></div>'+(hasSeparateRecommendation(r)?recommendationHTML(r):'')+(r.calibration?.previous_changed?diffHTML('与上一轮推荐的差异',data.previous_diff):'')+'<div class="detail-heading">相近消息 <span class="nls-muted">'+h(data.engine)+' · '+data.references.length+' 项</span><span class="nls-spacer"></span><button type="button" class="nls-btn nls-quiet" data-refresh>刷新检索</button></div>'+data.references.map(referenceHTML).join('')+(!data.references.length?'<p class="nls-muted">数据库中没有足够相近的消息。</p>':'')+'</div>';
 }
 async function expand(row,r,force=false){
  let details=$('details-'+r.id);const button=row.querySelector('[data-expand]');
  if(details&&!force){details.remove();button.setAttribute('aria-expanded','false');button.classList.remove('open');return}
  if(!details){details=document.createElement('tr');details.id='nls-details-'+r.id;details.className='details-row';details.dataset.id=r.id;row.after(details)}
  button.setAttribute('aria-expanded','true');button.classList.add('open');
  details.innerHTML='<td colspan="5"><div class="row-details nls-muted">正在查询相近消息…</div></td>';
  try{
   const data=await api('references/?id='+encodeURIComponent(r.id));
   if(!details.isConnected)return;
   details.innerHTML='<td colspan="5">'+detailsHTML(r,data)+'</td>';
   details.querySelector('[data-note]').value=r.note;
  }catch(e){details.innerHTML='<td colspan="5"><div class="nls-error">'+h(e.message)+'</div></td>'}
 }
 async function saveComponent(submit=false){
  for(const r of state.records)clearTimeout(r._timer);
  await Promise.all(state.records.map(r=>r._saving).filter(Boolean));
  const selected=submit?state.records:state.records.filter(r=>r._dirty);
  if(!selected.length){toast('所有修改已保存');return}
  const serials=new Map(selected.map(r=>[r.id,r._serial])),befores=new Map(selected.map(r=>[r.id,r._saved]));
  // 提交时未改动的行只传 id 和版本号，译文由服务器沿用。
  const decisions=selected.map(r=>r._dirty?decisionFor(r,submit?'approved':'pending'):{id:r.id,expected_version:r.version});
  const result=await api('save/',{component:state.component,submit,decisions});
  const items=[];
  for(const value of result.results){const r=state.byId.get(value.id);applySave(r,value,serials.get(r.id));r._error='';state.lastSaved=value.updated_at;refreshRow(r);items.push({id:r.id,before:befores.get(r.id),expected:value.version})}
  state.undo.push({items});progress();toast(submit?'组件已提交：'+n(selected.length)+' 条':'已保存 '+n(selected.length)+' 条修改');
 }
 // ---- 事件（全部限定在工具内部） ----
 let roToast=0;
 const readOnlyHint=()=>{if(Date.now()-roToast>2500){roToast=Date.now();toast('',true,'只读模式 — <a href="'+h(state.user.login_url)+'">登录</a>审校账号后才能校对或编辑')}};
 root.addEventListener('click',e=>{
  if(!canEdit()&&e.target.matches('[data-check]')){e.preventDefault();readOnlyHint();return}
  const component=e.target.closest('[data-component]');if(component){void run(async()=>{await flush();await loadComponent(component.dataset.component)});return}
  const row=e.target.closest('tr[data-id]'),r=row&&state.byId.get(row.dataset.id);
  if(r&&row.classList.contains('message-row'))setActive(r.id);
  const cell=e.target.closest('.editable');if(cell&&r){if(canEdit())editCell(cell,r);else readOnlyHint();return}
  if(e.target.closest('[data-expand]')&&r){void expand(row,r).catch(error);return}
  if(e.target.closest('[data-refresh]')&&r){void expand(rowEl(r.id),r,true).catch(error);return}
  if(e.target.closest('[data-adopt]')&&r){adoptRecommendation(r);return}
  if(r&&row.classList.contains('message-row')&&!e.target.closest('button,input,textarea,select,a,label')){rowCheckbox(r.id)?.focus({preventScroll:true})}
  const close=e.target.closest('[data-close]');if(close){document.getElementById(close.dataset.close).close();return}
 });
 $('export').addEventListener('click',e=>{e.preventDefault();void run(async()=>{await flush();const response=await fetch('/nls/api/export/',{headers:{'Accept':'application/json'}});if(!response.ok)throw new Error('导出失败（HTTP '+response.status+'）');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='pg19-human-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出当前审校状态')})});
 root.addEventListener('focusin',e=>{const row=e.target.closest?.('tr.message-row');if(row)setActive(row.dataset.id)});
 root.addEventListener('input',e=>{
  const row=e.target.closest('tr[data-id]'),r=row&&state.byId.get(row.dataset.id);if(!r)return;
  if(e.target.matches('textarea[data-edit]')){
   r.forms[e.target.dataset.edit]=e.target.value;
   const main=rowEl(r.id);if(main)paintOld(main,r,rowDiffs(r));
  }else if(e.target.matches('[data-note]'))r.note=e.target.value;else return;
  markDirty(r);
 });
 root.addEventListener('compositionstart',e=>{const r=state.byId.get(e.target.closest('tr[data-id]')?.dataset.id);if(r){r._composing=true;clearTimeout(r._timer)}});
 root.addEventListener('compositionend',e=>{const r=state.byId.get(e.target.closest('tr[data-id]')?.dataset.id);if(r){r._composing=false;markDirty(r)}});
 root.addEventListener('focusout',e=>{
  if(!e.target.matches('textarea[data-edit]'))return;
  const row=e.target.closest('tr[data-id]'),r=row&&state.byId.get(row.dataset.id);if(!r)return;
  const k=e.target.dataset.edit,diffs=rowDiffs(r);
  e.target.insertAdjacentHTML('afterend',editableHTML(r,k,r._index,diffs[k]));e.target.remove();
  paintOld(row,r,diffs);
 });
 root.addEventListener('change',e=>{
  const row=e.target.closest('tr[data-id]'),r=row&&state.byId.get(row.dataset.id);if(!r)return;
  if(e.target.matches('[data-check]'))void setStatus(r,e.target.checked?'approved':'pending');
  else if(e.target.matches('[data-status]'))void setStatus(r,e.target.value);
 });
 document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'&&canEdit()&&root.contains(document.activeElement)){e.preventDefault();void run(()=>saveComponent());return}
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  const typing=e.target.matches?.('input,textarea,select');
  if(e.key==='Escape'&&isFull()&&!typing&&!document.querySelector('dialog[open]')){e.preventDefault();setFullscreen(false);return}
  const row=e.target.closest?.('tr[data-id]'),r=row&&state.byId.get(row.dataset.id);
  if(e.target.matches?.('[data-check]')&&r){
   if(e.key===' '&&!canEdit()){e.preventDefault();readOnlyHint();return}
   if(e.key==='ArrowDown'||e.key==='j'){e.preventDefault();const el=siblingRow(row,1);if(el)focusRow(el.dataset.id)}
   else if(e.key==='ArrowUp'||e.key==='k'){e.preventDefault();const el=siblingRow(row,-1);if(el)focusRow(el.dataset.id)}
   else if(e.key==='Enter'||e.key==='F2'){e.preventDefault();editCell(row.querySelector('.editable'),r)}
   else if(e.key==='ArrowRight'||e.key==='l'){e.preventDefault();if(!$('details-'+r.id))void expand(row,r).catch(error)}
   else if(e.key==='ArrowLeft'||e.key==='h'){e.preventDefault();if($('details-'+r.id))void expand(row,r)}
   return;
  }
  if(e.target.matches?.('.editable')&&r&&['Enter','F2'].includes(e.key)){e.preventDefault();editCell(e.target,r);return}
  if(e.target.matches?.('textarea[data-edit]')&&r&&e.key==='Escape'){e.preventDefault();e.target.blur();focusRow(r.id,false);return}
  if((e.target===document.body||e.target===root)&&(e.key==='ArrowDown'||e.key==='j')){
   const first=(state.activeId&&rowEl(state.activeId))||$('rows').querySelector('tr.message-row');
   if(first){e.preventDefault();focusRow(first.dataset.id)}
  }
 });
 $('component-search').oninput=renderSidebar;
 $('search').oninput=()=>{clearTimeout(searchTimer);const q=$('search').value;searchTimer=setTimeout(()=>void run(async()=>{await flush();state.query=q;renderTable()}),250)};
 $('filter').onchange=()=>void run(async()=>{await flush();state.filter=$('filter').value;renderTable()});
 $('save-component').onclick=()=>void run(()=>saveComponent());
 $('submit-component').onclick=()=>{$('submit-error').hidden=true;$('submit-summary').textContent='将把 '+state.component+' 的全部 '+n(state.records.length)+' 条消息标记为已校对。';$('submit-dialog').showModal()};
 $('submit-confirm').onclick=()=>void run(async()=>{await saveComponent(true);$('submit-dialog').close()});
 $('undo').onclick=()=>void run(undo);
 window.addEventListener('beforeunload',e=>{if(state.records.some(r=>r._dirty||r._saving)){e.preventDefault();e.returnValue=''}});
 await run(async()=>{await bootstrap();if(!state.components.length){$('rows').innerHTML='<tr><td colspan="5" class="empty">尚未导入任何消息。</td></tr>';$('component-title').textContent='—';return}const previous=local.get('pgnls-table-component');await loadComponent(state.components.some(c=>c.name===previous)?previous:state.components[0].name)});
}
