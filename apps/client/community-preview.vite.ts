// Isolated local review; the normal server/browser at 5173/3001 stays running.
import base from './vite.config.ts';
export default {
    ...base,
    server: {...base.server,host:'127.0.0.2',port:5174,proxy:Object.fromEntries(Object.entries(base.server?.proxy??{}).map(([path,target])=>[path,typeof target==='string'?'http://127.0.0.1:3002':{...target,target:'ws://127.0.0.1:3002'}]))}
};
