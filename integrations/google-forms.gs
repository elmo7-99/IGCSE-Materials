// Specifically mapped to IGCSE Materials (الردود), read 2026-10-08.
// Bind to the existing spreadsheet. New registrations only; no historic bulk send.
const SOURCE_ID=PropertiesService.getScriptProperties().getProperty('SOURCE_SPREADSHEET_ID')||'';
const SOURCE_TAB=PropertiesService.getScriptProperties().getProperty('SOURCE_TAB')||'ردود النموذج 1';
const CONSENT_TITLE='WhatsApp order updates consent';
const CONSENT_CHOICE='I agree to receive WhatsApp updates about my book order / أوافق على تلقي تحديثات طلبي عبر واتساب';
function setupRegistrationAutomation(){
 const ss=SpreadsheetApp.getActiveSpreadsheet();
 if(ss.getId()!==SOURCE_ID)throw Error('Bind this script to the specified IGCSE spreadsheet.');
 const props=PropertiesService.getScriptProperties();
 if(!/^https:\/\//.test(props.getProperty('ORDERS_BASE_URL')||''))throw Error('Set a public HTTPS ORDERS_BASE_URL. localhost is not reachable from Google.');
 if((props.getProperty('INTAKE_API_KEY')||'').length<24)throw Error('Set INTAKE_API_KEY in Script Properties.');
 const formUrl=ss.getFormUrl();
 if(!formUrl)throw Error('No linked Form URL found; add the consent question manually.');
 const form=FormApp.openByUrl(formUrl);
 if(!form.getItems().some(x=>x.getTitle()===CONSENT_TITLE)){
  form.addCheckboxItem().setTitle(CONSENT_TITLE).setChoiceValues([CONSENT_CHOICE]).setRequired(true);
 }
 // Idempotent trigger setup: exactly one trigger of each type from this owner.
 const handlers=['onFormSubmit','retryQueue'];
 ScriptApp.getProjectTriggers().forEach(t=>{if(handlers.includes(t.getHandlerFunction()))ScriptApp.deleteTrigger(t);});
 ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(ss).onFormSubmit().create();
 ScriptApp.newTrigger('retryQueue').timeBased().everyMinutes(5).create();
 let q=ss.getSheetByName('AutomationQueue');if(!q){q=ss.insertSheet('AutomationQueue');q.appendRow(['source_id','payload','status','attempts','result','updated']);q.setFrozenRows(1);}
 console.log('New registrations are connected. Existing rows have not been sent.');
}
function registrationFromRow_(sheet,row){
 const headers=sheet.getRange(1,1,1,sheet.getLastColumn()).getDisplayValues()[0];
 const values=sheet.getRange(row,1,1,headers.length).getDisplayValues()[0];
 const get=title=>{const i=headers.indexOf(title);return i>=0?String(values[i]||'').trim():'';};
 const levels=headers.map((h,i)=>String(h).trim()==='?level'?String(values[i]||'').trim():'').filter(Boolean);
 if(levels.length>1&&new Set(levels).size>1)throw Error('Ambiguous level columns: review the registration.');
 const parent=get("Parent's Phone Number");
 if(!parent)throw Error('Parent phone missing; review instead of messaging another number.');
 return {source_id:SOURCE_ID+':'+sheet.getSheetId()+':'+row,name:get('Name'),phone:parent,student_phone:get("Student's Phone Number"),school:get('School\n')||get('School'),subject:get('Subject'),city:get('Emirate'),initial_address:get('Delivery Location'),package:levels[0]||'',teacher:'',lang:PropertiesService.getScriptProperties().getProperty('DEFAULT_LANGUAGE')||'en',consent:get(CONSENT_TITLE)===CONSENT_CHOICE};
}
function onFormSubmit(e){
 const sheet=e.range.getSheet();if(sheet.getParent().getId()!==SOURCE_ID||sheet.getName()!==SOURCE_TAB)return;
 const lock=LockService.getScriptLock();lock.waitLock(20000);
 try{
  let q=sheet.getParent().getSheetByName('AutomationQueue');if(!q){q=sheet.getParent().insertSheet('AutomationQueue');q.appendRow(['source_id','payload','status','attempts','result','updated']);}
  let d;try{d=registrationFromRow_(sheet,e.range.getRow());}catch(err){q.appendRow([SOURCE_ID+':'+sheet.getSheetId()+':'+e.range.getRow(),'','REVIEW',0,String(err),new Date()]);return;}
  q.appendRow([d.source_id,JSON.stringify(d),d.consent?'PENDING':'REVIEW',0,d.consent?'':'WhatsApp consent missing',new Date()]);
 }finally{lock.releaseLock();}
 retryQueue();
}
function retryQueue(){
 const lock=LockService.getScriptLock();if(!lock.tryLock(1000))return;
 try{
  const p=PropertiesService.getScriptProperties(),base=p.getProperty('ORDERS_BASE_URL'),key=p.getProperty('INTAKE_API_KEY');
  if(!base||!base.startsWith('https://')||!key)throw Error('Configure ORDERS_BASE_URL and INTAKE_API_KEY');
  const q=SpreadsheetApp.openById(SOURCE_ID).getSheetByName('AutomationQueue');if(!q||q.getLastRow()<2)return;
  const rows=q.getRange(2,1,q.getLastRow()-1,6).getValues();let count=0;
  for(let i=0;i<rows.length&&count<15;i++){
   const row=rows[i];if(row[2]!=='PENDING'||Number(row[3])>=10)continue;count++;
   let status='PENDING',result='';const attempts=Number(row[3])+1;
   try{const r=UrlFetchApp.fetch(base.replace(/\/$/,'')+'/api/intake',{method:'post',contentType:'application/json',headers:{Authorization:'Bearer '+key},payload:row[1],muteHttpExceptions:true});const code=r.getResponseCode();result=r.getContentText().slice(0,5000);status=code>=200&&code<300?'IMPORTED':code>=400&&code<500?'REVIEW':'PENDING';}
   catch(err){result=String(err).slice(0,500);}
   if(attempts>=10&&status==='PENDING')status='REVIEW';q.getRange(i+2,3,1,4).setValues([[status,attempts,result,new Date()]]);
  }
 }finally{lock.releaseLock();}
}
