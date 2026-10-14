'use strict';
(() => {
  const root=document.getElementById('comfort-profile'); if (!root) return;
  const base=root.dataset.apiBase, byId=id => document.getElementById(id);
  let profileRevision=0, contactId=null, contactRevision=0, checkedAccount=null;
  const make=(tag,text='') => { const node=document.createElement(tag); node.textContent=text; return node; };
  const say=text => { byId('profile-message').textContent=text; };
  async function api(path,options={}) {
    const response=await fetch(base+path,{...options,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',
      ...(options.method ? {'X-CSRFToken':document.querySelector('input[name=csrfmiddlewaretoken]').value} : {}),...options.headers}});
    const data=await response.json();
    if (!response.ok) throw new Error(response.status===401 ? 'Your session ended. Sign in again.' : response.status===404 ? 'This profile or contact is unavailable to your account.' : data.error==='invalid_request' ? 'Check the fields, date, ID type and contact email.' : data.error || 'Request failed.');
    return data;
  }
  const post=(path,data) => api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  async function run(action,button) {
    if (button) button.disabled=true;
    try { await action(); } catch(error) { say(error.message); }
    finally { if (button) button.disabled=false; }
  }
  const fields={full_name:'profile-full-name',preferred_name:'profile-preferred-name',email:'profile-email',phone:'profile-phone',address:'profile-address',gender:'profile-gender',identifier_type:'profile-id-type',identifier_number:'profile-id-number',identifier_issuer:'profile-id-issuer',blood_group:'profile-blood-group'};
  function adjustBirth() {
    const active={unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[byId('birth-precision').value];
    for (const part of ['year','month','day']) { byId('birth-'+part).disabled=!active.includes(part); byId('birth-'+part).required=active.includes(part); }
  }
  async function loadProfile() {
    byId('personal-fields').disabled=true;
    const data=await api('profile/'); profileRevision=data.revision;
    for (const [field,id] of Object.entries(fields)) byId(id).value=data.values[field];
    byId('birth-precision').value=data.values.birth_date.precision;
    for (const part of ['year','month','day']) byId('birth-'+part).value=data.values.birth_date[part] ?? '';
    byId('show-profile-id').checked=false; byId('profile-id-number').type='password'; adjustBirth();
    byId('personal-fields').disabled=false;
  }
  function clearContact() {
    contactId=null; contactRevision=0; checkedAccount=null; byId('contact-form').reset();
    byId('contact-editor-title').textContent='Add a contact'; byId('contact-account-preview').textContent='';
  }
  function editContact(item) {
    contactId=item.id; contactRevision=item.revision;
    for (const [field,id] of Object.entries({full_name:'contact-name',email:'contact-email',phone:'contact-phone',notes:'contact-notes',relationship:'contact-relationship'})) byId(id).value=item.values[field];
    byId('contact-next-of-kin').checked=item.values.is_next_of_kin; byId('contact-emergency').checked=item.values.is_emergency_contact;
    byId('contact-account').value=item.values.recipient_id || '';
    checkedAccount=item.values.recipient_id ? {id:item.values.recipient_id,name:item.linked_account_name} : null;
    byId('contact-account-preview').textContent=checkedAccount ? `${checkedAccount.name} · ${checkedAccount.id}${item.account_available ? '' : ' · Account unavailable'}` : '';
    byId('contact-editor-title').textContent='Edit this contact'; byId('contact-name').focus();
  }
  async function loadContacts() {
    const data=await api(`care-circle/?include_archived=${byId('show-archived-contacts').checked ? '1' : '0'}`), box=byId('care-circle-list'); box.replaceChildren();
    if (!data.contacts.length) box.append(make('p','No saved contacts yet.'));
    for (const item of data.contacts) {
      const row=make('article'); row.className='assistant-task';
      row.append(make('h3',item.values.full_name),make('p',`${item.values.relationship.replaceAll('_',' ')}${item.values.is_next_of_kin ? ' · Next of kin' : ''}${item.values.is_emergency_contact ? ' · Emergency contact' : ''}${item.status==='archived' ? ' · Removed' : ''}`));
      if (item.values.phone) row.append(make('p',item.values.phone)); if (item.values.email) row.append(make('p',item.values.email));
      if (item.values.notes) row.append(make('p',item.values.notes));
      if (item.values.recipient_id) row.append(make('p',`Linked account: ${item.linked_account_name}${item.account_available ? '' : ' (unavailable)'}. No access granted.`));
      if (item.status==='active') { const edit=make('button','Edit contact'); edit.type='button'; edit.className='secondary'; edit.addEventListener('click',() => editContact(item)); row.append(edit); }
      const status=make('button',item.status==='active' ? 'Remove from Care circle' : 'Restore contact'); status.type='button'; status.className='secondary';
      status.addEventListener('click',() => run(async () => {
        await post(`care-circle/${item.id}/status/`,{status:item.status==='active' ? 'archived' : 'active',expected_revision:item.revision});
        if (contactId===item.id) clearContact(); await loadContacts(); say(item.status==='active' ? 'Contact removed. Existing record permissions remain separate; manage them in Connect your care.' : 'Contact restored. No access granted.');
      },status)); row.append(status); box.append(row);
    }
  }
  byId('birth-precision').addEventListener('change',adjustBirth);
  byId('show-profile-id').addEventListener('change',() => { byId('profile-id-number').type=byId('show-profile-id').checked ? 'text' : 'password'; });
  byId('profile-id-type').addEventListener('change',() => {
    if (byId('profile-id-type').value==='none') { byId('profile-id-number').value=''; byId('profile-id-issuer').value=''; }
  });
  byId('reload-profile').addEventListener('click',event => run(loadProfile,event.currentTarget));
  byId('profile-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
    const values=Object.fromEntries(Object.entries(fields).map(([field,id]) => [field,byId(id).value.trim()]));
    const precision=byId('birth-precision').value, active={unknown:[],year:['year'],month:['year','month'],day:['year','month','day']}[precision];
    values.birth_date={precision,year:null,month:null,day:null}; for (const part of active) values.birth_date[part]=Number(byId('birth-'+part).value);
    const data=await post('profile/',{values,expected_revision:profileRevision}); profileRevision=data.revision;
    byId('show-profile-id').checked=false; byId('profile-id-number').type='password'; say('Your personal details are saved privately.');
  },event.submitter); });
  byId('contact-account').addEventListener('input',() => { checkedAccount=null; byId('contact-account-preview').textContent=''; });
  byId('check-contact-account').addEventListener('click',event => run(async () => {
    const requested=byId('contact-account').value.trim(); checkedAccount=null;
    if (!requested) throw new Error('Enter the person’s Comfort account ID, or leave it blank to save a contact without a link.');
    const target=await post('care-circle/resolve/',{recipient_id:requested});
    if (requested!==byId('contact-account').value.trim()) return;
    byId('contact-account').value=target.id; checkedAccount=target; byId('contact-account-preview').textContent=`${target.name} · ${target.id}. Check this is the intended person.`;
  },event.currentTarget));
  byId('contact-form').addEventListener('submit',event => { event.preventDefault(); run(async () => {
    const account=byId('contact-account').value.trim();
    if (account && (!checkedAccount || checkedAccount.id!==account)) throw new Error('Check the linked account before saving this contact.');
    const values={full_name:byId('contact-name').value.trim(),relationship:byId('contact-relationship').value,
      email:byId('contact-email').value.trim(),phone:byId('contact-phone').value.trim(),notes:byId('contact-notes').value.trim(),
      is_next_of_kin:byId('contact-next-of-kin').checked,is_emergency_contact:byId('contact-emergency').checked,recipient_id:account || null};
    await post(contactId ? `care-circle/${contactId}/` : 'care-circle/',{values,expected_revision:contactRevision});
    clearContact(); await loadContacts(); say('Care circle contact saved. No record access has been granted.');
  },event.submitter); });
  byId('new-contact').addEventListener('click',clearContact); byId('show-archived-contacts').addEventListener('change',() => run(loadContacts));
  run(async () => { await loadProfile(); await loadContacts(); });
})();
