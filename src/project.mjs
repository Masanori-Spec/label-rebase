import {analyze,rebase} from './core.mjs';
/** Parse only our own versioned, JSON-only project. Never restore stale results. */
export function parseProject(text){
 if(typeof text!=='string'||text.length>13000000||new TextEncoder().encode(text).length>13000000)throw Error('Project file exceeds 13 MB.');
 const data=JSON.parse(text);if(!data||data.format!=='label-rebase-project'||data.version!==1||!data.input||typeof data.input!=='object'||Array.isArray(data.input))throw Error('Unsupported LabelRebase project.');
 const input={oldCSV:data.input.oldCSV,newCSV:data.input.newCSV,oldCRS:data.input.oldCRS,newCRS:data.input.newCRS,oldMapping:data.input.oldMapping,newMapping:data.input.newMapping};
 for(const k of ['oldMapping','newMapping'])if(input[k]!==undefined&&(!input[k]||typeof input[k]!=='object'||Array.isArray(input[k])||Object.values(input[k]).some(v=>typeof v!=='string')))throw Error('Invalid project column mapping.');
 const decisions=data.decisions??{};if(!decisions||typeof decisions!=='object'||Array.isArray(decisions)||Object.values(decisions).some(v=>!['keep','follow','reset'].includes(v)))throw Error('Invalid project decisions.');
 analyze(input);rebase(input,decisions);return {input,decisions};
}
