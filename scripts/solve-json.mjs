import {rebase} from '../src/core.mjs';
let text='';for await(const c of process.stdin)text+=c;try{const i=JSON.parse(text);process.stdout.write(JSON.stringify(rebase(i,i.decisions||{})));}catch(e){process.stdout.write(JSON.stringify({ok:false,errors:[{code:e.code||'INPUT',message:e.message,...(e.key?{key:e.key}:{})}]}));}
