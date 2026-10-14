'use strict';
(() => {
  const patient = document.getElementById('comfort-workspace');
  const received = document.getElementById('comfort-received');
  if (!patient && !received) return;
  const byId = id => document.getElementById(id);
  const base = patient?.dataset.apiBase;
  const make = (tag,text='') => { const node=document.createElement(tag); node.textContent=text; return node; };
  const say = text => { byId('continuity-message').textContent=text; };
  const csrf = () => document.querySelector('input[name=csrfmiddlewaretoken]').value;
  async function api(url,options={}) {
    if (!url.startsWith('/api/')) throw new Error('Invalid application request.');
    const response=await fetch(url,{...options,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',
      ...(options.method && options.method!=='GET' ? {'X-CSRFToken':csrf()} : {}),...options.headers}});
    const data=await response.json();
    if (!response.ok) throw new Error(response.status===404 ? 'This permission or record is unavailable. It may have expired or been revoked.' :
      response.status===401 ? 'Your session ended. Sign in again.' : data.error==='invalid_request' ? 'Check the recipient, selection, purpose and expiry.' : data.error || 'Request failed.');
    return data;
  }
  const post = (url,value) => api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  function confirmAction(message) {
    return new Promise(resolve => {
      const previous=document.activeElement, dialog=make('dialog');
      dialog.setAttribute('aria-label','Confirm this action');
      dialog.append(make('h2','Confirm this action'),make('p',message));
      const cancel=make('button','Cancel'), confirm=make('button','Confirm');
      cancel.type='button'; cancel.className='secondary'; confirm.type='button';
      cancel.addEventListener('click',() => dialog.close('cancel'));
      confirm.addEventListener('click',() => dialog.close('confirm'));
      dialog.append(cancel,confirm); document.body.append(dialog);
      dialog.addEventListener('close',() => {
        const approved=dialog.returnValue==='confirm'; dialog.remove();
        if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
        resolve(approved);
      },{once:true});
      dialog.showModal(); cancel.focus();
    });
  }
  async function run(action,button) {
    if (button) button.disabled=true;
    try { await action(); } catch(error) { say(error.message); }
    finally { if (button) button.disabled=false; }
  }
  function link(url,label) {
    if (!url.startsWith('/api/') || url.startsWith('//')) throw new Error('Invalid original link.');
    const a=make('a',label); a.href=url; return a;
  }
  function dateText(value) {
    if (!value || value.precision==='unknown') return 'Date unknown';
    if (value.precision==='year') return `${value.year} (year only)`;
    if (value.precision==='month') {
      const months=['January','February','March','April','May','June','July','August','September','October','November','December'];
      return `${months[value.month-1]} ${value.year}`;
    }
    return `${value.year}-${String(value.month).padStart(2,'0')}-${String(value.day).padStart(2,'0')}`;
  }
  function options(id,items,empty) {
    const select=byId(id), previous=select.value;
    select.replaceChildren();
    const placeholder=make('option',empty); placeholder.value=''; select.append(placeholder);
    for (const item of items) { const option=make('option',item.label); option.value=item.id; select.append(option); }
    if (items.some(item => item.id===previous)) select.value=previous;
  }
  if (patient) {
    let selected=[], episodes=[], packets=[], checkedRecipient=null;
    document.addEventListener('comfort:selection-changed',event => { selected=event.detail; });
    function targets() {
      const items=byId('grant-kind').value==='read' ? packets : episodes;
      options('grant-target',items,items.length ? 'Choose the exact scope' : 'Create a packet or episode first');
    }
    async function load() {
      const [care,prepared,permissions,inbox]=await Promise.all([
        api(base+'episodes/'),api(base+'packets/'),api(base+'grants/'),api(base+'contributions/')]);
      episodes=care.episodes.map(e => ({id:e.id,label:e.title}));
      packets=[];
      for (const item of prepared.packets) {
        const packet=await api(base+`packets/${item.id}/`);
        packets.push({id:packet.revision_id,label:`${packet.purpose} (${packet.items.length} originals)`});
      }
      options('episode-link-target',episodes,'Choose an episode'); options('record-episode',episodes,'All episodes'); targets();
      try {
        const circle=await api(base+'care-circle/choices/');
        options('grant-care-contact',circle.contacts.map(c => ({id:c.recipient_id,label:`${c.name} · ${c.relationship.replaceAll('_',' ')} · account: ${c.account_name}`})),'Choose a saved contact, or enter an account ID below');
      } catch { options('grant-care-contact',[],'Care circle unavailable; enter the exact account ID below'); }
      const grants=byId('grant-list'); grants.replaceChildren(make('h3','Approved permissions'));
      if (!permissions.grants.length) grants.append(make('p','No permissions granted.'));
      for (const grant of permissions.grants) {
        const row=make('article'); row.className='assistant-task';
        row.append(make('p',`${grant.kind==='read' ? 'Read packet' : 'Submit note'} · ${grant.recipient_name} · ${grant.purpose}`),
          make('p',`${grant.state} · expires ${new Date(grant.expires_at).toLocaleString()}`));
        if (grant.state==='active') {
          const revoke=make('button','Revoke this permission'); revoke.type='button'; revoke.className='secondary';
          revoke.addEventListener('click',() => run(async () => {
            if (!await confirmAction(`Revoke ${grant.kind==='read' ? 'read access' : 'contribution permission'} for ${grant.recipient_name}? The other permission remains separate.`)) return;
            await post(base+`grants/${grant.kind}/${grant.id}/revoke/`,{}); await load(); say('Permission revoked.');
          },revoke)); row.append(revoke);
        }
        grants.append(row);
      }
      const box=byId('contribution-inbox'); box.replaceChildren();
      if (!inbox.contributions.length) box.append(make('p','No submitted notes yet.'));
      for (const item of inbox.contributions) {
        const row=make('article'); row.className='assistant-task';
        row.append(make('h4',item.original_filename),make('p',`${item.submitted_by_name} · ${item.state}`),
          link(base+`contributions/${item.id}/original/`,'Download submitted original'));
        if (item.state==='pending') for (const decision of ['accept','reject']) {
          const button=make('button',decision==='accept' ? 'Accept into my records' : 'Reject this note'); button.type='button'; button.className='secondary';
          button.addEventListener('click',() => run(async () => {
            if (!await confirmAction(`${decision==='accept' ? 'Accept' : 'Reject'} ${item.original_filename} from ${item.submitted_by_name}? This decision is final for this submission.`)) return;
            await post(base+`contributions/${item.id}/review/`,{decision}); await load(); byId('refresh-records').click();
            say(decision==='accept' ? 'Note accepted into its episode with the original submitter’s attribution.' : 'Note rejected; it remains outside your record history.');
          },button)); row.append(button);
        }
        box.append(row);
      }
    }
    byId('grant-recipient').addEventListener('input',() => { checkedRecipient=null; byId('recipient-preview').textContent=''; byId('grant-confirm').checked=false; });
    byId('grant-care-contact').addEventListener('change',() => {
      if (!byId('grant-care-contact').value) return;
      byId('grant-recipient').value=byId('grant-care-contact').value;
      byId('grant-recipient').dispatchEvent(new Event('input')); byId('check-recipient').click();
    });
    byId('check-recipient').addEventListener('click',event => run(async () => {
      const id=byId('grant-recipient').value.trim(); checkedRecipient=null;
      const target=await post(base+'recipients/resolve/',{recipient_id:id});
      if (id!==byId('grant-recipient').value.trim()) return;
      checkedRecipient=target; byId('recipient-preview').textContent=`${target.name} · ${target.id}. Account identity only; credentials not verified.`;
    },event.currentTarget));
    byId('grant-kind').addEventListener('change',() => { targets(); byId('grant-confirm').checked=false; });
    for (const id of ['grant-target','grant-purpose','grant-minutes']) byId(id).addEventListener('change',() => { byId('grant-confirm').checked=false; });
    byId('grant-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
      if (!checkedRecipient || checkedRecipient.id!==byId('grant-recipient').value.trim() || !byId('grant-confirm').checked) throw new Error('Check the recipient and confirm this permission first.');
      const target=byId('grant-target').selectedOptions[0]?.textContent;
      const payload={kind:byId('grant-kind').value,target_id:byId('grant-target').value,
        recipient_id:checkedRecipient.id,purpose:byId('grant-purpose').value.trim(),expires_in_minutes:Number(byId('grant-minutes').value)};
      if (!await confirmAction(`Approve ${payload.kind==='read' ? 'read access' : 'note submission'} for ${checkedRecipient.name}, scope: ${target}, purpose: ${payload.purpose}, for ${payload.expires_in_minutes} minutes?`)) return;
      await post(base+'grants/',payload);
      byId('grant-confirm').checked=false; await load(); say('Permission approved. The recipient can open Received access.');
    },event.submitter); });
    byId('episode-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
      await post(base+'episodes/',{title:byId('episode-title').value.trim()}); byId('episode-title').value=''; await load(); say('Care episode created.');
    },event.submitter); });
    byId('episode-link-sources').addEventListener('click',event => run(async () => {
      if (!selected.length || !byId('episode-link-target').value) throw new Error('Select records above and choose an episode.');
      await post(base+`episodes/${byId('episode-link-target').value}/sources/`,{source_version_ids:selected}); await load(); say('Selected originals linked to this episode.');
    },event.currentTarget));
    byId('refresh-continuity').addEventListener('click',event => run(load,event.currentTarget));
    document.addEventListener('comfort:packets-changed',() => run(load)); run(load);
  } else {
    let signature=null, timer=null;
    async function load(force=false) {
      let data;
      try { data=await api('/api/continuity/received/'); }
      catch(error) { byId('received-grants').replaceChildren(); signature=null; throw error; }
      const next=JSON.stringify(data);
      if (!force && signature===next) return;
      signature=next;
      const box=byId('received-grants'); box.replaceChildren();
      if (!data.grants.length) box.append(make('p','No active patient permissions. Expired and revoked access is unavailable.'));
      for (const grant of data.grants) {
        const row=make('section'); row.className='panel';
        row.append(make('h2',`${grant.kind==='read' ? 'Shared records' : 'Submit a note'} · ${grant.patient_name}`),
          make('p',grant.purpose),make('p',`Expires ${new Date(grant.expires_at).toLocaleString()}`));
        if (grant.kind==='read') {
          const view=make('button','Open selected records'); view.type='button';
          const sources=make('div');
          view.addEventListener('click',() => run(async () => {
            sources.replaceChildren();
            const packet=await api(`/api/continuity/shares/${grant.id}/`);
            for (const item of packet.items) sources.append(make('p',item.original_filename),
              make('p',`${item.metadata.document_type?.replaceAll('_',' ') || 'Type unknown'} · ${item.metadata.facility_name || 'Facility unknown'} · ${dateText(item.metadata.document_date)}`),
              link(item.download_url,'Download this selected original'));
            sources.append(make('p','This grant permits selected originals only. It does not authorize submitting notes.'));
          },view)); row.append(view,sources);
        } else {
          row.append(make('p',`Episode: ${grant.episode_title}. This permission gives no access to patient records.`));
          const form=make('form'), label=make('label','Original note file'), file=make('input');
          file.type='file'; file.accept='.pdf,.jpg,.jpeg,.png,.dcm,.dicom'; file.required=true;
          label.append(file); form.append(label);
          const kindLabel=make('label','Image purpose'), kind=make('select');
          for (const [value,text] of [['document','Written report / photographed document'],['medical_image','Medical image export']]) {
            const option=make('option',text); option.value=value; kind.append(option);
          }
          kindLabel.append(kind); form.append(kindLabel);
          const submit=make('button','Submit for patient review'); submit.type='submit'; form.append(submit);
          form.addEventListener('submit',event => { event.preventDefault(); run(async () => {
            const original=file.files[0]; if (!original || !original.size || original.size>10485760) throw new Error('Choose one nonempty original up to 10 MB.');
            const suffix=original.name.split('.').pop().toLowerCase();
            const payload=new FormData(); payload.append('file',original); payload.append('content_kind',suffix==='pdf' ? 'document' : ['dcm','dicom'].includes(suffix) ? 'medical_image' : kind.value);
            await api(`/api/continuity/contribution-authorities/${grant.id}/submit/`,{method:'POST',body:payload});
            file.value=''; await load(true); say('Original submitted. It stays pending until the patient reviews it.');
          },submit); }); row.append(form);
          for (const item of grant.submissions) row.append(make('p',`${item.original_filename} · ${item.state}`));
        }
        box.append(row);
      }
    }
    byId('refresh-received').addEventListener('click',event => run(() => load(true),event.currentTarget));
    run(async () => { const account=await api('/api/continuity/account/'); byId('comfort-account-id').textContent=`${account.name} · ${account.id}`; await load(); });
    timer=setInterval(() => run(load),15000);
    window.addEventListener('pagehide',() => clearInterval(timer));
  }
})();
