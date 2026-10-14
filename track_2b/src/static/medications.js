'use strict';
(() => {
  const root=document.getElementById('comfort-medications'); if (!root) return;
  const base=root.dataset.apiBase, byId=id => document.getElementById(id);
  let entryId=null, revision=0, offset=0, sourceOffset=0, sources=[], requestNumber=0;
  const fields={medicine_name:'medicine-name',dose:'medicine-dose',frequency:'medicine-frequency',route:'medicine-route',instructions:'medicine-instructions',use_status:'medicine-use'};
  const useNames={reported_taken:'Taken / taking — patient reported',reported_prescribed:'Prescribed — taking not confirmed',not_taken:'Not taken — patient reported',unknown:'Taking not specified'};
  const make=(tag,text='') => { const node=document.createElement(tag); node.textContent=text; return node; };
  const say=text => { byId('medication-message').textContent=text; };
  async function api(path,options={}) {
    const response=await fetch(base+path,{...options,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',
      ...(options.method ? {'X-CSRFToken':document.querySelector('input[name=csrfmiddlewaretoken]').value} : {}),...options.headers}});
    const data=await response.json();
    if (!response.ok) throw new Error(response.status===401 ? 'Your session ended. Sign in again.' : response.status===404 ? 'This entry or linked record is unavailable to your account.' : data.error==='invalid_request' ? 'Check the medicine, date and selected original.' : data.error || 'Request failed.');
    return data;
  }
  const post=(path,data) => api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  async function run(action,button) { if (button) button.disabled=true; try { await action(); } catch(error) { say(error.message); } finally { if (button) button.disabled=false; } }
  function adjustDate() {
    const active={unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[byId('medicine-date-precision').value];
    for (const part of ['year','month','day']) { byId('medicine-'+part).disabled=!active.includes(part); byId('medicine-'+part).required=active.includes(part); }
  }
  function dateText(date) { return date.precision==='unknown' ? 'Date unknown' : [date.year,...(date.month===null ? [] : [String(date.month).padStart(2,'0')]),...(date.day===null ? [] : [String(date.day).padStart(2,'0')])].join('-'); }
  function option(select,id,label) { const node=make('option',label); node.value=id; select.append(node); }
  function clear() { entryId=null; revision=0; byId('medication-form').reset(); byId('medication-editor-title').textContent='Add a medication entry'; adjustDate(); }
  function edit(item) {
    entryId=item.id; revision=item.revision;
    for (const [field,id] of Object.entries(fields)) byId(id).value=item.values[field];
    const date=item.values.visit_date; byId('medicine-date-precision').value=date.precision;
    for (const part of ['year','month','day']) byId('medicine-'+part).value=date[part] ?? '';
    if (item.values.source_version_id && !Array.from(byId('medicine-source').options).some(o => o.value===item.values.source_version_id)) option(byId('medicine-source'),item.values.source_version_id,item.source_filename || 'Previously linked original');
    if (item.values.episode_id && !Array.from(byId('medicine-episode').options).some(o => o.value===item.values.episode_id)) option(byId('medicine-episode'),item.values.episode_id,item.episode_title || 'Previously linked episode');
    byId('medicine-source').value=item.values.source_version_id || ''; byId('medicine-episode').value=item.values.episode_id || '';
    adjustDate(); byId('medication-editor-title').textContent='Edit this medication entry'; byId('medicine-name').focus();
  }
  async function loadChoices(more=false) {
    const data=await api(`medications/choices/?offset=${more ? sourceOffset : 0}`);
    if (!more) {
      sources=[]; sourceOffset=0; const previous=byId('medicine-episode').value, previousLabel=byId('medicine-episode').selectedOptions[0]?.textContent;
      byId('medicine-episode').replaceChildren(); option(byId('medicine-episode'),'','No episode selected');
      for (const e of data.episodes) option(byId('medicine-episode'),e.id,e.title);
      if (previous && !data.episodes.some(e => e.id===previous)) option(byId('medicine-episode'),previous,previousLabel || 'Previously linked episode');
      byId('medicine-episode').value=previous;
    }
    const previous=byId('medicine-source').value, previousLabel=byId('medicine-source').selectedOptions[0]?.textContent; sources.push(...data.sources); sourceOffset+=data.sources.length;
    byId('medicine-source').replaceChildren(); option(byId('medicine-source'),'','No original linked');
    for (const s of sources) option(byId('medicine-source'),s.id,`${s.filename} · version ${s.version_number}`);
    if (previous && !sources.some(s => s.id===previous)) option(byId('medicine-source'),previous,previousLabel || 'Previously linked original');
    byId('medicine-source').value=previous; byId('more-medication-sources').hidden=data.sources.length<data.limit;
  }
  async function load(more=false) {
    const token=++requestNumber, start=more ? offset : 0;
    const data=await api(`medications/?include_archived=${byId('show-archived-medications').checked ? '1' : '0'}&offset=${start}`);
    if (token!==requestNumber) return;
    const box=byId('medication-list'); if (!more) box.replaceChildren();
    if (!data.medications.length && !more) box.append(make('p','No medication entries yet.'));
    for (const item of data.medications) {
      const row=make('article'); row.className='assistant-task'; const value=item.values;
      row.append(make('h3',value.medicine_name),make('p',`${useNames[value.use_status]}${item.status==='archived' ? ' · Archived' : ''}`),make('p',`${dateText(value.visit_date)}${item.episode_title ? ' · '+item.episode_title : ''}`));
      for (const [field,label] of [['dose','Dose / strength'],['frequency','Frequency'],['route','How taken'],['instructions','Instructions / notes']]) if (value[field]) row.append(make('p',`${label}: ${value[field]}`));
      if (item.source_download_url && item.source_download_url.startsWith(base+'versions/')) { const link=make('a',`Open original: ${item.source_filename}`); link.href=item.source_download_url; row.append(link); }
      if (item.status==='active') { const button=make('button','Edit entry'); button.type='button'; button.className='secondary'; button.addEventListener('click',() => edit(item)); row.append(button); }
      const status=make('button',item.status==='active' ? 'Archive entry' : 'Restore entry'); status.type='button'; status.className='secondary'; status.addEventListener('click',() => run(async () => {
        await post(`medications/${item.id}/status/`,{status:item.status==='active' ? 'archived' : 'active',expected_revision:item.revision});
        if (entryId===item.id) clear(); await load(); say(item.status==='active' ? 'Entry archived. Its original remains unchanged.' : 'Entry restored.');
      },status)); row.append(status); box.append(row);
    }
    offset=start+data.medications.length; byId('more-medications').hidden=data.medications.length<data.limit;
  }
  byId('medication-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
    const values=Object.fromEntries(Object.entries(fields).map(([field,id]) => [field,byId(id).value.trim()]));
    const precision=byId('medicine-date-precision').value, active={unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[precision];
    values.visit_date={precision,year:null,month:null,day:null}; for (const part of active) values.visit_date[part]=Number(byId('medicine-'+part).value);
    values.episode_id=byId('medicine-episode').value || null; values.source_version_id=byId('medicine-source').value || null;
    await post(entryId ? `medications/${entryId}/` : 'medications/',{values,expected_revision:revision}); clear(); await load(); say('Your patient-reported medication entry is saved.');
  },event.submitter); });
  byId('medicine-date-precision').addEventListener('change',adjustDate); byId('new-medication').addEventListener('click',clear);
  byId('show-archived-medications').addEventListener('change',() => run(load)); byId('refresh-medications').addEventListener('click',event => run(load,event.currentTarget));
  byId('more-medications').addEventListener('click',event => run(() => load(true),event.currentTarget)); byId('more-medication-sources').addEventListener('click',event => run(() => loadChoices(true),event.currentTarget));
  adjustDate(); run(async () => { await load(); await loadChoices(); });
})();
