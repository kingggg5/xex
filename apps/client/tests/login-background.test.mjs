import assert from "node:assert/strict";
import { test } from "node:test";
import { mountLoginBackground } from "../src/login-background.ts";

// Exercise ownership and scheduling without a browser/GPU or auth side effects.
test("login decoration pauses, follows motion preferences, and disposes all observers/listeners", () => {
  const originals = new Map();
  const install = (key, value) => { originals.set(key, Object.getOwnPropertyDescriptor(globalThis,key)); Object.defineProperty(globalThis,key,{configurable:true,writable:true,value}); };
  const listeners = new Set(), observers = [], pending = new Map(); let next = 0;
  class Element {
    dataset={}; children=[]; hidden=false; isConnected=true; lang="en"; clientWidth=390; clientHeight=844;
    addEventListener(type, callback) { listeners.add({owner:this,type,callback}); }
    removeEventListener(type, callback) { for (const item of listeners) if(item.owner===this && item.type===type && item.callback===callback) listeners.delete(item); }
    dispatch(type) { for (const item of [...listeners]) if(item.owner===this && item.type===type) item.callback({preventDefault(){}}); }
    setAttribute(name,value) { this[name]=value; }
    append(...children) { this.children.push(...children); }
    prepend(child) { this.children.unshift(child); }
    querySelector(selector) { return selector===".login-shell"?this:this.children.find(child=>child.className===selector.slice(1))??null; }
    getContext() { return null; }
    remove() { this.isConnected=false; }
  }
  class Observer {
    constructor(callback) { this.callback=callback; this.disconnected=false; observers.push(this); }
    observe() {}
    disconnect() { this.disconnected=true; }
  }
  const documentStub=new Element(); documentStub.visibilityState="visible"; documentStub.createElement=()=>new Element();
  const windowStub=new Element(), media=new Element(); media.matches=true;
  try {
    install("document",documentStub); install("window",windowStub); install("matchMedia",()=>media);
    for (const name of ["ResizeObserver","MutationObserver","IntersectionObserver"]) install(name,Observer);
    install("requestAnimationFrame",callback=>{pending.set(++next,callback); return next;});
    install("cancelAnimationFrame",id=>pending.delete(id));
    const screen=new Element(), stop=mountLoginBackground(screen);
    const stage=screen.children[0], button=screen.children.find(child=>child.className==="login-motion-toggle");
    assert.equal(pending.size,0,"reduced motion must not start a decorative loop");
    button.dispatch("click"); assert.equal(pending.size,1,"explicit opt-in starts one loop even with reduced-motion preference");
    assert.equal(stage.dataset.renderer,"static","missing WebGL never blocks the login controls");
    assert.equal(stage.dataset.buffer,"390x844");
    documentStub.visibilityState="hidden"; documentStub.dispatch("visibilitychange");
    assert.equal(pending.size,0,"background tab must cancel scheduled work");
    documentStub.visibilityState="visible"; documentStub.dispatch("visibilitychange"); assert.equal(pending.size,1);
    screen.hidden=true; observers[1].callback(); assert.equal(pending.size,0,"hidden login must not render over gameplay");
    screen.hidden=false; observers[1].callback(); assert.equal(pending.size,1);
    media.dispatch("change"); assert.equal(pending.size,0,"new reduced-motion preference takes effect immediately");
    media.matches=false; media.dispatch("change"); assert.equal(pending.size,1);
    button.dispatch("click"); assert.equal(pending.size,0);
    button.dispatch("click"); assert.equal(pending.size,1);
    windowStub.dispatch("pagehide"); assert.equal(pending.size,0);
    windowStub.dispatch("pageshow"); assert.equal(pending.size,1,"BFCache return resumes without a duplicate loop");
    stop(); stop();
    assert.equal(pending.size,0); assert.equal(listeners.size,0);
    assert.ok(observers.every(observer=>observer.disconnected));
    assert.ok(!stage.isConnected && !button.isConnected);
  } finally {
    for (const [key,descriptor] of originals) { if(descriptor) Object.defineProperty(globalThis,key,descriptor); else delete globalThis[key]; }
  }
});
