/** LabelRebase: original stable-key reconciliation, no provider FIDs. */
export class InputError extends Error { constructor(code,message,key){super(message);this.code=code;this.key=key;} }
const fail=(code,msg,key)=>{throw new InputError(code,msg,key);};
export const DEFAULT_OLD={key:'key',x:'x',y:'y',labelX:'label_x',labelY:'label_y',rotation:'rotation',show:'show'};
export const DEFAULT_NEW={key:'key',x:'x',y:'y',text:'text'};
export function parseCSV(text){
 if(typeof text!=='string'||text.length>2000000)fail('CSV_SIZE','CSV must be text and no larger than 2 MB.');
 text=text.replace(/^\uFEFF/,'');if(!text)fail('CSV_EMPTY','CSV is empty.');
 const rows=[];let row=[],cell='',quoted=false,closed=false,atStart=true;
 for(let i=0;i<text.length;i++){const c=text[i];
  if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
  if(c==='"'){if(!atStart||closed)fail('CSV_QUOTE','Unexpected quote.');quoted=true;atStart=false;continue;}
  if(c===','||c==='\n'||c==='\r'){row.push(cell);cell='';closed=false;atStart=true;if(c!==','){if(c==='\r'&&text[i+1]==='\n')i++;rows.push(row);row=[];}continue;}
  if(closed)fail('CSV_QUOTE','Characters after a closing quote.');cell+=c;atStart=false;
 }
 if(quoted)fail('CSV_QUOTE','Unclosed quoted field.');if(row.length||cell||closed)rows.push([...row,cell]);
 const headers=rows.shift();if(!headers?.length||headers.some(h=>!h.trim()))fail('CSV_HEADER','Every column needs a name.');
 if(new Set(headers).size!==headers.length)fail('DUPLICATE_HEADER','Column names must be unique.');
 if(rows.length>5000)fail('ROW_LIMIT','Limit: 5,000 data rows per CSV.');
 rows.forEach((r,i)=>{if(r.length!==headers.length)fail('CSV_WIDTH',`CSV row ${i+2} has ${r.length} fields; expected ${headers.length}.`);});
 return {headers,rows};
}
function dec(value,label){
 const s=String(value);if(s!==s.trim()||!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/.test(s))fail('INVALID_NUMBER',`${label} must be a finite decimal.`);
 const [m,e='0']=s.toLowerCase().split('e'),parts=m.replace(/^[-+]/,'').split('.');const exponent=Number(e);
 if(Math.abs(exponent)>30||(parts.join('').length)>30)fail('NUMBER_RANGE',`${label} exceeds the supported precision (30 digits/exponent).`);
 let n=BigInt(parts.join(''))*(m[0]==='-'?-1n:1n),scale=(parts[1]?.length||0)-exponent;if(scale<0){n*=10n**BigInt(-scale);scale=0;}
 while(scale&&n%10n===0n){n/=10n;scale--;}
 return {n,scale};
}
function str(d){let neg=d.n<0n,s=(neg?-d.n:d.n).toString();if(d.scale){s=s.padStart(d.scale+1,'0');s=s.slice(0,-d.scale)+'.'+s.slice(-d.scale);}return (neg?'-':'')+s;}
function op(a,b,sign=1n){const x=dec(a,'coordinate'),y=dec(b,'coordinate'),scale=Math.max(x.scale,y.scale);return str({n:x.n*10n**BigInt(scale-x.scale)+sign*y.n*10n**BigInt(scale-y.scale),scale});}
export const decimalAdd=(a,b)=>str(dec(op(a,b),'sum'));
export const decimalSubtract=(a,b)=>str(dec(op(a,b,-1n),'difference'));
function num(s,what){const d=dec(s,what);if(!Number.isFinite(Number(s))||Math.abs(Number(s))>1e12)fail('NUMBER_RANGE',`${what} must be within ±10¹².`);return str(d);}
function crs(s){const m=/^EPSG:(\d+)$/.exec(s||'');const n=m?Number(m[1]):0;if(!(n===3857||n===3395||(n>=32601&&n<=32660)||(n>=32701&&n<=32760)))fail('CRS_UNSUPPORTED','Choose a supported projected CRS: EPSG:3857, EPSG:3395, or WGS 84 UTM EPSG:32601–32660 / 32701–32760.');return s;}
function inputRows(csv,map,isOld){const parsed=parseCSV(csv),required=isOld?['key','x','y','labelX','labelY']:['key','x','y','text'];
 for(const field of required)if(!map[field]||!parsed.headers.includes(map[field]))fail('MAPPING',`Map ${isOld?'old':'new'} ${field} to an existing column.`);
 for(const field of isOld?['rotation','show']:[])if(map[field]&&!parsed.headers.includes(map[field]))fail('MAPPING',`The optional ${field} column does not exist.`);
 const active=Object.values(map).filter(Boolean);if(new Set(active).size!==active.length)fail('MAPPING_DUPLICATE','Map each role to a distinct column.');
 const seen=new Set(),rows=[];
 for(const values of parsed.rows){const get=f=>map[f]?values[parsed.headers.indexOf(map[f])]:'',key=get('key');
  if(!key.trim()||/[\r\n\x00-\x1f]/.test(key))fail('KEY_MISSING','Stable keys must be nonblank single-line strings.');if(seen.has(key))fail('DUPLICATE_KEY',`Duplicate stable key: ${key}`,key);seen.add(key);
  const r={key,x:num(get('x'),`${key} point X`),y:num(get('y'),`${key} point Y`)};
  if(isOld){const a=get('labelX'),b=get('labelY');if((a==='')!==(b===''))fail('LABEL_PAIR',`Both label coordinates must be present or both blank: ${key}`,key);r.labelX=a===''?'':num(a,`${key} label X`);r.labelY=b===''?'':num(b,`${key} label Y`);r.rotation=get('rotation')===''?'0':num(get('rotation'),`${key} rotation`);if(Math.abs(Number(r.rotation))>360)fail('ROTATION_RANGE','Rotation must be between -360 and 360 degrees.',key);const v=get('show');if(!['','1','0','true','false','TRUE','FALSE'].includes(v))fail('VISIBILITY','Visibility must be 1, 0, true, false, or blank.',key);r.show=['0','false','FALSE'].includes(v)?'0':'1';}
  else{r.text=get('text');if(!r.text.trim()||/[\r\n\x00-\x1f]/.test(r.text))fail('LABEL_TEXT','Label text must be nonblank single-line text.',key);if(r.text.length>500)fail('TEXT_LIMIT','Limit: 500 characters per label.',key);}
  rows.push(r);
 }
 if(!rows.length)fail('CSV_EMPTY','At least one data row is required.');return rows;
}
export function analyze(input){
 const oldCRS=crs(input.oldCRS),newCRS=crs(input.newCRS);if(oldCRS!==newCRS)fail('CRS_MISMATCH','Old and new coordinates must declare the same projected CRS. No reprojection is performed.');
 const oldMapping={...DEFAULT_OLD,...input.oldMapping},newMapping={...DEFAULT_NEW,...input.newMapping};
 const oldRows=inputRows(input.oldCSV,oldMapping,true),newRows=inputRows(input.newCSV,newMapping,false),oldByKey=new Map(oldRows.map(r=>[r.key,r])),newKeys=new Set(newRows.map(r=>r.key));
 const changes=newRows.map(n=>{const o=oldByKey.get(n.key),moved=o&&(o.x!==n.x||o.y!==n.y),pinned=o&&o.labelX!=='';return {key:n.key,old:o||null,new:n,status:o?(moved?'moved':'unchanged'):'new',requiresDecision:!!(moved&&pinned),dx:o?decimalSubtract(n.x,o.x):'0',dy:o?decimalSubtract(n.y,o.y):'0'};});
 return {crs:oldCRS,oldMapping,newMapping,oldRows,newRows,changes,removed:oldRows.filter(r=>!newKeys.has(r.key)).map(r=>r.key)};
}
export function rebase(input,decisions={}){
 const a=analyze(input),pending=a.changes.filter(c=>c.requiresDecision&&!Object.hasOwn(decisions,c.key));if(pending.length)fail('DECISION_REQUIRED',`Choose a movement policy for ${pending.map(c=>c.key).join(', ')}.`);
 for(const [key,choice] of Object.entries(decisions)){const c=a.changes.find(c=>c.key===key);if(!c?.requiresDecision||!['keep','follow','reset'].includes(choice))fail('INVALID_DECISION',`Unexpected decision for ${key}.`,key);}
 const rows=a.changes.map(c=>{const o=c.old,choice=c.requiresDecision?decisions[c.key]:(o?'unchanged':'new'),pin=o?.labelX!==''&&!!o&&choice!=='reset';let x=pin?o.labelX:'',y=pin?o.labelY:'';
  if(pin&&choice==='follow'){x=decimalAdd(x,c.dx);y=decimalAdd(y,c.dy);num(x,'rebased label X');num(y,'rebased label Y');}
  return {stable_key:c.key,point_x:c.new.x,point_y:c.new.y,label_text:c.new.text,label_x:x,label_y:y,label_rotation:o&&choice!=='reset'?o.rotation:'0',label_show:o?.show??'1',label_state:pin?'pinned':'auto',decision:choice};});
 return {ok:true,crs:a.crs,rows,removed:a.removed,added:a.changes.filter(c=>c.status==='new').map(c=>c.key),decisions:Object.fromEntries(a.changes.filter(c=>c.requiresDecision).map(c=>[c.key,decisions[c.key]])),oldMapping:a.oldMapping,newMapping:a.newMapping};
}
