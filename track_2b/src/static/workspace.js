'use strict';
(() => {
  const root = document.getElementById('comfort-workspace');
  if (!root) return;
  const base = root.dataset.apiBase;
  const byId = id => document.getElementById(id);
  const selected = new Set();
  const pollers = new Map();
  let proposalId = null;
  let facilitySelection;
  let facilityLocation = null;
  let uploading = false;
  let failedUploads = [];
  let recordsPoller = null;
  let recordsOffset = 0;
  let keywordQuery = '';
  const stateText = {queued:'Queued for processing', processing:'Processing', waiting_model:'Waiting for model access',
    needs_ocr:'Text extraction from this scan is not available yet', manual_review:'Ready for your review',
    review_ready:'Metadata suggestions are ready', completed:'Suggestions ready', failed:'Processing did not complete'};
  const make = (tag, text = '', className = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const say = text => { byId('workspace-message').textContent = text; };
  const csrf = () => document.querySelector('input[name=csrfmiddlewaretoken]').value;
  async function api(path, options = {}) {
    const headers = {'Accept':'application/json', ...options.headers};
    if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
    const response = await fetch(base + path, {...options, headers, credentials:'same-origin', cache:'no-store'});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) throw new Error('Your session ended. Sign in again.');
      if (response.status === 404) throw new Error('This record or action is not available to your account.');
      if (response.status === 400) throw new Error(data.error && data.error !== 'invalid_request' ? data.error : 'Check your inputs, file format and limits.');
      throw new Error(data.error || 'The request could not be completed.');
    }
    return data;
  }
  const post = (path, value) => api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  function guardedLink(path, label) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith(base)) throw new Error('Invalid source link.');
    const anchor = make('a',label); anchor.href = url.href; return anchor;
  }
  function mapsLink(value, label = 'Open saved facility pin') {
    const text = (value || '').trim();
    if (!text || text.length > 2048 || /[\s\\]/.test(text)) throw new Error('Use a Google Maps place or Share link.');
    const url = new URL(text);
    if (url.protocol !== 'https:' || url.username || url.password || url.port ||
        !/^https:\/\/((www\.)?google\.com\/maps(\/|\?|$)|maps\.google\.com(\/|\?|$)|maps\.app\.goo\.gl\/[A-Za-z0-9_-]+(\/|\?|$)|goo\.gl\/maps\/[A-Za-z0-9_-]+(\/|\?|$))/.test(url.href)) throw new Error('Use a Google Maps place or Share link.');
    const anchor = make('a',label); anchor.href = url.href; anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer'; anchor.referrerPolicy = 'no-referrer'; return anchor;
  }
  function clearFacilitySelection() {
    facilitySelection = null; facilityLocation = null;
    byId('review-facility-maps').value = ''; showFacilityPin();
  }
  function showFacilityPin() {
    const box = byId('facility-pin-preview'); box.replaceChildren();
    if (!byId('review-facility-maps').value.trim()) return;
    if (facilityLocation) box.append(make('p',`${facilityLocation.name} · ${facilityLocation.address}`));
    try { box.append(mapsLink(byId('review-facility-maps').value,'Check this facility pin')); }
    catch { box.append(make('p','Paste the Google Maps place URL or Share link.','quiet')); }
  }
  function dateText(value) {
    if (!value || value.precision === 'unknown') return 'Date unknown';
    const parts = [value.year];
    if (value.month !== null) parts.push(String(value.month).padStart(2,'0'));
    if (value.day !== null) parts.push(String(value.day).padStart(2,'0'));
    return parts.join('-');
  }
  function selectionCount() {
    byId('selection-count').textContent = selected.size ? `${selected.size} source version${selected.size === 1 ? '' : 's'} selected.` : 'No records selected.';
  }
  async function loadRecords(append = false) {
    if (recordsPoller) { clearTimeout(recordsPoller); recordsPoller = null; }
    if (!append) { recordsOffset = 0; byId('record-list').replaceChildren(); }
    const data = await api(`records/?q=${encodeURIComponent(keywordQuery)}&offset=${recordsOffset}`);
    if (!data.records.length && !append) byId('record-list').append(make('p', keywordQuery ? 'No keyword matches. Try another term or Ask Apertus.' : 'No health records here yet. Add an original above.'));
    for (const record of data.records) {
      const version = record.current_version;
      const row = make('div','','record-row');
      const check = document.createElement('input'); check.type = 'checkbox'; check.id = `select-${version.id}`;
      check.checked = selected.has(version.id);
      check.addEventListener('change',() => { check.checked ? selected.add(version.id) : selected.delete(version.id); selectionCount(); });
      const label = document.createElement('label'); label.htmlFor = check.id;
      label.append(make('span', version.original_filename,'record-name'));
      const values = record.metadata.values;
      label.append(make('span',`${values.document_type || 'Type not confirmed'} · ${dateText(values.document_date)} · ${values.facility_name || 'Facility not confirmed'}`,'quiet'));
      label.append(make('span',` · ${stateText[record.jobs[0]?.state] || 'Original saved'}`,'quiet'));
      const open = make('button','Review','secondary'); open.type = 'button';
      open.addEventListener('click',() => run(() => showRecord(record.id)));
      row.append(check,label,open);
      if (record.metadata.facility_maps_url) row.append(mapsLink(record.metadata.facility_maps_url,'Facility pin'));
      byId('record-list').append(row);
    }
    recordsOffset += data.records.length;
    byId('more-records').hidden = data.records.length < data.limit;
    selectionCount();
    if (recordsOffset <= 50 && data.records.some(record => ['queued','processing','waiting_model'].includes(record.jobs[0]?.state)))
      recordsPoller = setTimeout(() => run(loadRecords),5000);
  }
  function fillReview(values) {
    byId('review-type').value = values.document_type || 'other';
    if (byId('review-facility').value !== (values.facility_name || '')) clearFacilitySelection();
    byId('review-facility').value = values.facility_name || '';
    showFacilityPin();
    const date = values.document_date || {precision:'unknown',year:null,month:null,day:null};
    byId('review-precision').value = date.precision;
    for (const part of ['year','month','day']) byId(`review-${part}`).value = date[part] ?? '';
    adjustDate();
  }
  function adjustDate() {
    const parts = {unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[byId('review-precision').value];
    for (const part of ['year','month','day']) {
      byId(`review-${part}`).disabled = !parts.includes(part);
      byId(`review-${part}`).required = parts.includes(part);
    }
  }
  function citations(parent, items) {
    for (const citation of items || []) {
      const block = make('div','','citation');
      block.append(make('p',citation.quote));
      block.append(guardedLink(citation.download_url, `Open ${citation.original_filename}`));
      const locator = citation.locator;
      block.append(make('p',locator.kind === 'source_text' ? `Source page ${locator.page}` : `${locator.kind.replaceAll('_',' ')}${locator.field ? ': '+locator.field : ''}`,'quiet'));
      parent.append(block);
    }
  }
  async function showRecord(id) {
    const record = await api(`records/${id}/`);
    const version = record.current_version;
    proposalId = null;
    byId('review-record-id').value = record.id; byId('review-version-id').value = version.id;
    byId('review-revision').value = record.metadata.revision;
    fillReview(record.metadata.values);
    facilitySelection = undefined;
    facilityLocation = record.metadata.facility_location;
    byId('facility-query').value = record.metadata.values.facility_name || '';
    byId('facility-results').replaceChildren();
    byId('review-facility-maps').value = record.metadata.facility_maps_url || '';
    showFacilityPin();
    byId('source-details').replaceChildren(make('h3',version.original_filename),guardedLink(version.download_url,'Download the exact original'),make('p',`Version ${version.version_number} · ${stateText[record.jobs[0]?.state] || 'Original saved'}`,'quiet'));
    byId('source-preview').replaceChildren();
    if (version.image_details_url) {
      const image = await api(`versions/${version.id}/image/`);
      if (image.details) {
        if (image.preview_url) {
          const preview = document.createElement('img'); preview.src = image.preview_url;
          preview.alt = 'Small record preview; use the original for clinical viewing'; preview.className = 'image-preview';
          byId('source-preview').append(preview,make('p','Preview for organization only. Original bytes are preserved.','quiet'));
        } else byId('source-preview').append(make('p','DICOM original preserved. Open the download in a suitable DICOM viewer.','quiet'));
        for (const [field,item] of Object.entries(image.details.header_fields || {})) byId('source-preview').append(make('p',`${field}: ${item.value} (source header, not confirmed)`,'quiet'));
      } else byId('source-preview').append(make('p',stateText[image.state] || 'Image inspection pending','quiet'));
    }
    byId('metadata-proposals').replaceChildren();
    for (const proposal of record.proposals) {
      const box = make('div','','citation');
      box.append(make('p',`Apertus metadata suggestion (${proposal.model}). Review the source evidence before confirming.`));
      for (const [field,evidence] of Object.entries(proposal.values.evidence || {})) if (evidence) box.append(make('p',`${field}: page ${evidence.page} — ${evidence.quote}`,'quiet'));
      const use = make('button','Review this suggestion','secondary'); use.type = 'button';
      use.addEventListener('click',() => { fillReview(proposal.values); proposalId = proposal.id; say('Suggestion loaded into the review form. Check each field before confirming.'); });
      box.append(use); byId('metadata-proposals').append(box);
    }
    byId('record-details').hidden = false;
    byId('record-details').scrollIntoView({block:'start'});
  }
  async function loadPackets() {
    const data = await api('packets/'); byId('packet-list').replaceChildren();
    for (const packet of data.packets) {
      const row = make('div','','assistant-task'); row.append(make('h3',packet.purpose));
      const overview = make('button','Draft an overview with Apertus','secondary'); overview.type = 'button';
      overview.addEventListener('click',() => run(() => submitTask('packet_overview',{packet_id:packet.id})));
      const inspect = make('button','See selected originals','secondary'); inspect.type = 'button';
      inspect.addEventListener('click',() => run(async () => {
        const content = await api(`packets/${packet.id}/`);
        const list = make('div'); for (const item of content.items) {
          list.append(make('p'),guardedLink(item.source_version.download_url,item.source_version.original_filename));
          if (item.facility_maps_url) list.append(make('p'),mapsLink(item.facility_maps_url,'Facility pin saved in this packet'));
        }
        row.append(list); inspect.disabled = true;
      }));
      const actions = make('div','','actions'); actions.append(inspect,overview); row.append(actions); byId('packet-list').append(row);
    }
  }
  function showTask(task) {
    let box = byId(`task-${task.id}`);
    if (!box) { box = make('article','','assistant-task'); box.id = `task-${task.id}`; byId('assistant-results').prepend(box); }
    box.replaceChildren(make('h3',({search:'Record search',packet_overview:'Consultation overview',explain_term:'Term explanation'})[task.kind]), make('p',task.result?.limitation_code === 'no_readable_report_text' ? 'Written report needed' : (stateText[task.state] || task.state),'task-status'));
    if (task.state === 'waiting_model') box.append(make('p','This request is saved. It can run once Apertus access is configured. No generated answer is available yet.'));
    if (task.state === 'failed') {
      const errors = {cancelled_by_user:'Request cancelled.',invalid_model_output:'Apertus returned an answer that failed the format or source-evidence checks. It was not saved as a suggestion. You can try a new request.',
        model_access_failed:'The Apertus server could not be reached or rejected the request. Your originals are still available.',
        processing_timeout:'This request took too long. Try a smaller selection of records.',authority_unavailable:'Access changed before the request finished.'};
      box.append(make('p',errors[task.error_code] || 'The assistant could not produce a usable result. Originals remain available; you can make another request.'));
    }
    if (task.kind === 'packet_overview' && task.coverage.text_available_sources === 0) box.append(make('p','No readable report text was included. This text model cannot read MRI/ultrasound pixels or photographed text.','quiet'));
    if (['queued','processing','waiting_model'].includes(task.state)) {
      const cancel = make('button','Cancel request','secondary'); cancel.type = 'button';
      cancel.addEventListener('click',() => run(async () => showTask(await post(`assistant/tasks/${task.id}/cancel/`,{})))); box.append(cancel);
    }
    if (task.sources.some(source => !source.current_version || source.metadata_changed_since_request)) box.append(make('p','Some records changed after this request. Suggestions refer to the saved versions and details.','quiet'));
    if (task.kind === 'search') box.append(make('p',`${task.coverage.included_records} of ${task.coverage.accessible_records_at_request} records included; ${task.coverage.text_available_sources} had readable report text when requested. ${task.coverage.truncated_sources} source contexts were shortened; images were not analyzed.`,'quiet'));
    const result = task.result;
    if (result) {
      if (result.limitation_code === 'no_readable_report_text') box.append(make('p','An overview needs a written report. This packet contains only image records without readable report text. Add the written imaging report, then create a new packet. No model generation or image interpretation was performed.'));
      else if (result.abstained) box.append(make('p','Apertus did not find enough supporting evidence to answer.'));
      for (const match of result.matches || []) { box.append(make('p',match.reason)); citations(box,match.citations); }
      if (result.status === 'draft_for_patient_review') box.append(make('p','Draft for your review — the packet is unchanged.'));
      for (const item of result.items || []) { box.append(make('p',item.text)); citations(box,item.citations); }
      if (result.explanation) {
        box.append(make('p',result.explanation)); citations(box,result.citations);
        const reference = make('a',result.reference.title); reference.href = result.reference.url; reference.rel = 'noreferrer';
        box.append(reference,make('p',result.scope,'quiet'));
      }
    }
    if (pollers.has(task.id)) { clearTimeout(pollers.get(task.id)); pollers.delete(task.id); }
    if (['queued','processing','waiting_model'].includes(task.state)) pollers.set(task.id,setTimeout(() => run(async () => showTask(await api(`assistant/tasks/${task.id}/`))),task.state === 'waiting_model' ? 15000 : 2500));
  }
  async function submitTask(kind, parameters) {
    const task = await post('assistant/tasks/',{kind,parameters}); showTask(task);
    say('Assistant request saved. Its status and sources appear below.');
  }
  async function run(action, button) {
    if (button) button.disabled = true;
    try { await action(); } catch (error) { say(error.message || 'The request failed.'); }
    finally { if (button) button.disabled = false; }
  }
  async function uploadFiles(files,kind) {
    if (uploading) return;
    if (!files.length || files.length > 30) throw new Error('Choose between one and 30 files.');
    uploading = true; failedUploads = []; byId('retry-uploads').hidden = true;
    byId('record-file').disabled = true; byId('record-kind').disabled = true;
    const submit = byId('upload-form').querySelector('button[type=submit]'); submit.disabled = true;
    byId('upload-results').replaceChildren(); let saved = 0;
    try {
      for (const [index,file] of files.entries()) {
        const row = make('p',`${index+1}/${files.length} · ${file.name} · Uploading…`,'quiet'); byId('upload-results').append(row);
        try {
          if (!file.size || file.size > 10*1024*1024) throw new Error('Choose a nonempty file up to 10 MB.');
          const suffix = file.name.split('.').pop().toLowerCase();
          const contentKind = suffix === 'pdf' ? 'document' : ['dcm','dicom'].includes(suffix) ? 'medical_image' : kind;
          const form = new FormData(); form.append('file',file); form.append('content_kind',contentKind);
          const data = await api('records/',{method:'POST',body:form}); saved++;
          row.textContent = `${file.name} · ${data.created ? 'Original saved' : 'Already saved in your workspace'}`;
        } catch (error) { failedUploads.push({file,kind}); row.textContent = `${file.name} · Not saved: ${error.message}`; }
      }
      byId('record-file').value = ''; byId('upload-selection').textContent = 'Choose up to 30 files.';
      keywordQuery = ''; await loadRecords();
      say(`${saved} of ${files.length} files saved or already present.${failedUploads.length ? ' Retry failed files when ready.' : ' Processing status appears in your record list.'}`);
    } finally {
      uploading = false; submit.disabled = false; byId('record-file').disabled = false; byId('record-kind').disabled = false;
      byId('retry-uploads').hidden = !failedUploads.length;
    }
  }
  byId('record-file').addEventListener('change',() => {
    const files = Array.from(byId('record-file').files);
    byId('upload-selection').textContent = `${files.length} file${files.length === 1 ? '' : 's'} selected. Up to 30 files, 10 MB each.`;
  });
  byId('upload-form').addEventListener('submit',event => { event.preventDefault(); run(() => uploadFiles(Array.from(byId('record-file').files),byId('record-kind').value)); });
  byId('retry-uploads').addEventListener('click',() => run(() => uploadFiles(failedUploads.map(item => item.file),failedUploads[0]?.kind || 'document')));
  byId('search-form').addEventListener('submit', event => { event.preventDefault(); run(async () => {
    const query = byId('record-query').value.trim();
    if (event.submitter?.value === 'apertus') { if (!query) throw new Error('Enter a record-search request.'); await submitTask('search',{query}); }
    else { keywordQuery = query; await loadRecords(); }
  },event.submitter); });
  byId('reset-search').addEventListener('click',() => run(async () => { keywordQuery = ''; byId('record-query').value = ''; await loadRecords(); }));
  byId('refresh-records').addEventListener('click',() => run(loadRecords));
  byId('more-records').addEventListener('click',() => run(() => loadRecords(true)));
  byId('review-precision').addEventListener('change',adjustDate);
  byId('review-facility').addEventListener('input',() => {
    if (byId('review-facility-maps').value) say('Facility name changed. Choose its pin again before confirming.');
    clearFacilitySelection();
  });
  byId('clear-facility-pin').addEventListener('click',clearFacilitySelection);
  byId('facility-query').addEventListener('input',() => byId('facility-results').replaceChildren());
  byId('facility-query').addEventListener('keydown',event => {
    if (event.key === 'Enter') { event.preventDefault(); if (!byId('facility-search').disabled) byId('facility-search').click(); }
  });
  byId('facility-search').addEventListener('click',event => run(async () => {
    const query = byId('facility-query').value.trim();
    if (query.length < 3) throw new Error('Enter a hospital name, adding its town to distinguish branches.');
    const version = byId('review-version-id').value;
    byId('facility-results').replaceChildren(make('p','Searching hospitals…','quiet'));
    try {
      const data = await post('facilities/search/',{query});
      if (version !== byId('review-version-id').value || query !== byId('facility-query').value.trim()) return;
      const box = byId('facility-results'); box.replaceChildren();
      if (!data.results.length) box.append(make('p','No matching healthcare facilities found. Try the hospital’s full name and town.','quiet'));
      for (const place of data.results) {
        const row = make('div','','citation'); row.append(make('h3',place.name),make('p',place.address,'quiet'));
        const select = make('button','Choose this hospital','secondary'); select.type = 'button';
        select.addEventListener('click',() => {
          facilitySelection = place.selection_token; facilityLocation = place;
          byId('review-facility').value = place.name;
          byId('review-facility-maps').value = place.maps_url;
          showFacilityPin(); box.replaceChildren(); say('Hospital selected. Confirm these details to save its location.');
        });
        row.append(select,mapsLink(place.maps_url,'View pin')); box.append(row);
      }
    } catch (error) { byId('facility-results').replaceChildren(make('p',error.message,'quiet')); throw error; }
  },event.currentTarget));
  byId('review-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
    const precision = byId('review-precision').value;
    const parts = {unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[precision];
    const date = {precision,year:null,month:null,day:null};
    for (const part of parts) date[part] = Number(byId(`review-${part}`).value);
    const payload = {source_version_id:byId('review-version-id').value,expected_revision:Number(byId('review-revision').value),
      facility_maps_url:byId('review-facility-maps').value.trim() || null,
      values:{document_type:byId('review-type').value,document_date:date,facility_name:byId('review-facility').value.trim() || null}};
    if (facilitySelection !== undefined) payload.facility_selection = facilitySelection;
    if (payload.facility_maps_url) {
      mapsLink(payload.facility_maps_url);
      if (!payload.values.facility_name) throw new Error('Enter the issuing facility name for this pin.');
    }
    if (proposalId) payload.proposal_id = proposalId;
    const id = byId('review-record-id').value;
    await post(`records/${id}/review/`,payload); await loadRecords(); await showRecord(id); say('Your review was saved with correction history.');
  },event.submitter); });
  byId('term-form').addEventListener('submit',event => { event.preventDefault(); run(() => submitTask('explain_term',{source_version_id:byId('review-version-id').value,term:byId('record-term').value.trim()}),event.submitter); });
  byId('packet-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
    if (!selected.size || selected.size > 30) throw new Error('Select between one and 30 source versions.');
    await post('packets/',{purpose:byId('packet-purpose').value.trim(),source_version_ids:Array.from(selected)});
    selected.clear(); await loadRecords(); await loadPackets(); say('Private packet created with exactly the selected originals.');
  },event.submitter); });
  run(async () => {
    await loadRecords(); await loadPackets();
    const status = await api('assistant/status/');
    if (status.configured) byId('assistant-availability').textContent = status.text_only ?
      'Local Apertus text inference is configured. Search uses written text and record details; image pixels are not analyzed. Check each suggestion against its sources.' :
      'Apertus inference is configured. Check each suggestion against its sources. Image understanding is not part of this text assistant.';
    const history = await api('assistant/tasks/'); for (const task of history.tasks.slice().reverse()) showTask(task);
  });
})();
