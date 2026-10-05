import path from 'node:path';
export function resolveStaticPath(directory,requestUrl,prefix='/'){
 const root=path.resolve(directory),pathname=decodeURIComponent(new URL(requestUrl,'http://localhost').pathname);
 if(!prefix.startsWith('/')||!prefix.endsWith('/'))throw Error('Invalid mount');
 if(!pathname.startsWith(prefix))throw Error('Outside mount');
 const target=path.resolve(root,pathname.slice(prefix.length)||'.');
 if(target!==root&&!target.startsWith(root+path.sep))throw Error('Outside root');return target;
}
