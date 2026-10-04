/** Decorative login-only renderer. Auth/UI stay DOM-based and usable without WebGL. */
const VERTEX = `#version 300 es
in vec2 position;
out vec2 uv;
void main(){ uv = position*.5+.5; gl_Position=vec4(position,0.,1.); }`;
// Light-only pass: the canvas is screen-blended over the art (login-theme.css), so the shader
// emits light (portal energy, flames, flicker) and never paints opaque colour over the painting.
const FRAGMENT = `#version 300 es
precision highp float;
in vec2 uv;
out vec4 color;
uniform vec2 viewport;
uniform vec2 imageSize;
uniform float time;
const float TAU=6.2831853;
float hash(vec2 p){ vec3 p3=fract(vec3(p.xyx)*.1031); p3+=dot(p3,p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
float noise(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f); return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y); }
float fbm(vec2 p){ float v=0.,a=.5; for(int i=0;i<4;i++){ v+=a*noise(p); p=mat2(1.6,1.2,-1.2,1.6)*p+vec2(3.1,1.7); a*=.5; } return v/.9375; }
float fbm3(vec2 p){ float v=0.,a=.5; for(int i=0;i<3;i++){ v+=a*noise(p); p=mat2(1.6,1.2,-1.2,1.6)*p+vec2(3.1,1.7); a*=.5; } return v/.875; }
// Angle-periodic noise for the log-polar vortex, so there is no seam where atan wraps.
float pnoise(vec2 p,float period){ vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f); float x0=mod(i.x,period),x1=mod(i.x+1.,period);
  return mix(mix(hash(vec2(x0,i.y)),hash(vec2(x1,i.y)),f.x),mix(hash(vec2(x0,i.y+1.)),hash(vec2(x1,i.y+1.)),f.x),f.y); }
float pfbm(vec2 p,float period){ return .55*pnoise(p,period)+.3*pnoise(p*2.+vec2(0,7.3),period*2.)+.15*pnoise(p*4.+vec2(0,3.1),period*4.); }
vec3 fireRamp(float h){ return vec3(1.5*h,1.5*h*h*h,h*h*h*h*h*h); }
vec3 brazier(vec2 P,vec2 origin,float seed){
  vec2 d=P-origin; // image-height units, +y down; origin is the back of the bowl rim
  if(abs(d.x)>.36 || d.y<-.45 || d.y>.2) return vec3(0.);
  float t=time+seed*7.31;
  float flick=.84+.08*sin(t*7.9)+.05*sin(t*13.3+1.7)+.18*(noise(vec2(t*4.3,seed*9.))-.5);
  // Flicker light thrown on the guardian, the gilded bowl and the floor.
  vec2 g=(d+vec2(0.,.075))*vec2(1.,.8); float r2=dot(g,g);
  float win=(1.-smoothstep(.24,.36,abs(d.x)))*smoothstep(-.45,-.3,d.y)*(1.-smoothstep(.12,.2,d.y)); // no seam at the box edge
  vec3 e=vec3(1.,.45,.16)*(exp(-r2*60.)*.13+exp(-r2*8.)*.07)*flick*win;
  float rim=exp(-pow((d.y-.009)/.007,2.))*(1.-smoothstep(.075,.11,abs(d.x)));
  e+=vec3(1.,.62,.28)*rim*.2*flick;
  vec2 q=vec2(d.x/.1,-d.y/.13); // flame space: x across the bowl, y up from the rim
  if(abs(q.x)<1.3 && q.y>-.12 && q.y<1.3){
    vec2 s=vec2(q.x*1.6,q.y*.9-t*1.5);
    vec2 w=vec2(fbm(s*1.3+seed*3.),fbm(s*1.3+vec2(5.2,seed)))-.5;
    float n=fbm(s*2.4+w*1.7);
    float y=max(q.y+.15,0.);
    float sx=q.x+(w.x*.5+sin(t*1.9+seed*4.)*.07)*y*y; // tongues lean and sway as they rise
    float body=length(vec2(sx*(1.+y*1.3),q.y-.2));
    float c=1.-pow(max(0.,body-n*y*.5)*1.6,1.3);
    float heat=clamp(n*c*1.6*(1.-smoothstep(.5,1.2,q.y)),0.,1.);
    heat*=smoothstep(-.12,.04,q.y); // the front of the bowl hides the flame's root
    e+=fireRamp(heat)*(.78+.3*flick);
  }
  return e;
}
vec3 astralDoor(vec2 q,float r,float fw){
  if(r>1.5) return vec3(0.);
  float a=atan(q.y,q.x);
  vec2 dir=q/max(r,1e-4);
  float pulse=.8+.13*sin(time*1.27)+.07*sin(time*2.71+1.1);
  vec3 e=vec3(0.);
  if(r>.1 && r<1.04){
    // Log-spiral vortex drifting inward: rigid in log-polar space, so it never winds up over time.
    float lr=log(r);
    float sw=pfbm(vec2(a/TAU*7.+lr*2.2-time*.07,lr*2.6+time*.33),7.);
    float vein=pow(1.-abs(2.*sw-1.),9.)*(.35+.65*smoothstep(.3,.7,pnoise(vec2(a/TAU*14.-time*.2,lr*5.+time*.6),14.)));
    float cloud=smoothstep(.5,1.,sw);
    float m=smoothstep(.15,.65,r)*(1.-smoothstep(.9,1.03,r));
    vec3 hue=mix(vec3(.4,.16,.95),vec3(.2,.6,1.),smoothstep(.3,.8,sw));
    e+=(hue*(vein*.7+cloud*.26)+vec3(.5,.7,1.)*vein*vein*.25)*m*pulse;
    // Sparse star motes pulled toward the centre, slightly stretched along their fall.
    vec2 cell=vec2(a/TAU*26.+time*.04,lr*6.+time*.8);
    vec2 id=vec2(mod(floor(cell.x),26.),floor(cell.y));
    float h=hash(id);
    if(h>.86){
      vec2 o=fract(cell)-.5-(vec2(hash(id+.37),hash(id+.71))-.5)*.5; o.y*=.5;
      float tw=.55+.45*sin(time*6.+h*40.);
      vec3 tint=mix(vec3(.55,.72,1.),vec3(.82,.6,1.),hash(id+.13));
      e+=tint*exp(-dot(o,o)*120.)*tw*.4*smoothstep(.15,.45,r)*(1.-smoothstep(.85,.98,r));
    }
  }
  float dr=r-.985;
  if(abs(dr)<.1){
    // Rim lightning: jagged arcs that strike in flickering segments, a creeping vein
    // network, and surges circulating the ring. Sampled on dir/iso so nothing seams at atan's wrap.
    vec2 iso=q*vec2(.242,.374); // height units: isotropic around the ellipse
    float n1=fbm3(dir*3.2+vec2(time*.8,-time*.6));
    float n2=fbm3(dir*5.7+vec2(-time*1.15,time*.9)+9.1);
    float jag1=noise(iso*55.+vec2(0.,time*6.))+.5*noise(iso*130.-vec2(time*9.,0.))-.75;
    float jag2=noise(iso*70.-vec2(time*7.,0.))+.5*noise(iso*150.+vec2(0.,time*11.))-.75;
    float w=max(fw*1.2,.003);
    float l1=w/(abs(dr+.012-(n1-.5)*.1-jag1*.03)+w);
    float l2=w/(abs(dr-.006-(n2-.5)*.07-jag2*.025)+w);
    float gate1=smoothstep(.38,.62,noise(dir*2.3+vec2(time*1.1,time*.7)));
    float gate2=smoothstep(.42,.6,noise(dir*3.1-vec2(time*1.7,time*1.3)+5.));
    float rv=1.-abs(2.*fbm3(iso*16.+vec2(time*.35,-time*.5))-1.);
    float veins=pow(rv,16.)*(1.-smoothstep(.0,.08,abs(dr+.025)));
    float surge=pow(.5+.5*sin(a*3.+n1*5.-time*2.1),3.);
    float crackle=smoothstep(.4,.85,noise(dir*7.+vec2(time*9.,0.)));
    float bolt=l1*l1*gate1*(.55+surge)+l2*l2*gate2*.7*(.4+crackle)+veins*(.25+.5*crackle);
    float fall=1.-smoothstep(.04,.1,abs(dr));
    e+=(vec3(.5,.74,1.)*bolt+vec3(.95,.97,1.)*pow(l1,6.)*gate1*.7*(.3+surge))*fall*pulse;
  }
  // Breathing rim halo; the outer tail spills light onto the gilded frame.
  e+=vec3(.28,.45,1.)*(exp(-dr*dr*160.)*.18+exp(-max(dr,0.)*11.)*smoothstep(.8,1.,r)*.1)*pulse;
  return e;
}
vec3 floorMist(vec2 p,float aspect){
  float fx=(p.x-.5)*aspect;
  float band=smoothstep(.8,.845,p.y)*(1.-smoothstep(.875,.965,p.y));
  float spread=exp(-fx*fx*6.)*(1.-smoothstep(.42,.6,abs(fx)));
  if(abs(fx)>.6 || band<.002) return vec3(0.);
  // Mist rolls out of the doorway in both directions along the floor.
  float m1=fbm3(vec2(fx*6.-time*.32,p.y*30.-time*.15));
  float m2=fbm3(vec2(fx*6.+time*.32,p.y*30.-time*.15)+4.4);
  float wisps=smoothstep(.32,.85,mix(m2,m1,smoothstep(-.05,.05,fx)));
  float glow=exp(-fx*fx*22.-pow((p.y-.872)/.028,2.))*(.8+.2*sin(time*1.27));
  return vec3(.42,.42,1.)*(wisps*.65*band*spread+glow*.12);
}
void main(){
  float scale=max(viewport.x/imageSize.x,viewport.y/imageSize.y);
  vec2 size=imageSize*scale;
  vec2 pixel=vec2(uv.x,1.-uv.y)*viewport;
  vec2 p=(pixel+(size-viewport)*.5)/size;
  float aspect=imageSize.x/imageSize.y;
  // Calibrated to the delivered art, not to the image-generation prompt.
  vec2 q=(p-vec2(.5,.477))/vec2(.136,.374);
  float r=length(q);
  float fw=fwidth(r); // before any branching: derivatives need uniform control flow
  // The braziers never overlap, so each pixel only evaluates the nearer one.
  float side=step(.5,p.x);
  vec3 e=astralDoor(q,r,fw)+floorMist(p,aspect)+brazier(p*vec2(aspect,1.),vec2(mix(.228,.771,side)*aspect,.78),side);
  e=clamp(e,0.,1.);
  float alpha=max(e.r,max(e.g,e.b));
  if(alpha<.004){ color=vec4(0.); return; }
  e=clamp(e+(hash(gl_FragCoord.xy)-.5)/255.,0.,1.); // dither the soft glows against banding
  alpha=max(e.r,max(e.g,e.b));
  // Straight alpha: composited with mix-blend-mode: screen this is exactly screen(art, e).
  color=vec4(e/alpha,alpha);
}`;

interface PortalPass { draw(time: number, width: number, height: number): void; dispose(): void }

function createPortal(canvas: HTMLCanvasElement): PortalPass | null {
  const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: false,
    antialias: false, depth: false, stencil: false, powerPreference: "low-power" });
  if (!gl) return null;
  const shaders: WebGLShader[] = [];
  let program: WebGLProgram | null = null;
  let buffer: WebGLBuffer | null = null;
  let vao: WebGLVertexArrayObject | null = null;
  const dispose = (): void => {
    if (gl.isContextLost()) return;
    shaders.forEach(shader => gl.deleteShader(shader));
    gl.deleteBuffer(buffer); gl.deleteVertexArray(vao); gl.deleteProgram(program);
  };
  try {
    for (const [type, source] of [[gl.VERTEX_SHADER, VERTEX], [gl.FRAGMENT_SHADER, FRAGMENT]] as const) {
      const shader = gl.createShader(type);
      if (!shader) throw new Error("Shader allocation failed");
      shaders.push(shader); gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? "Shader compile failed");
    }
    program = gl.createProgram();
    if (!program) throw new Error("Program allocation failed");
    shaders.forEach(shader => gl.attachShader(program!, shader)); gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error("Portal link failed");
    vao = gl.createVertexArray(); buffer = gl.createBuffer();
    if (!vao || !buffer) throw new Error("Portal buffer allocation failed");
    gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const resolution = gl.getUniformLocation(program, "viewport");
    const clock = gl.getUniformLocation(program, "time");
    const image = gl.getUniformLocation(program, "imageSize");
    return { dispose, draw(time, width, height) {
      if (gl.isContextLost()) return;
      gl.viewport(0, 0, canvas.width, canvas.height); gl.useProgram(program);
      gl.bindVertexArray(vao); gl.uniform2f(resolution, width, height);
      gl.uniform2f(image, 1672, 941); gl.uniform1f(clock, time);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }};
  } catch {
    dispose(); return null; // Static artwork plus embers remain usable on unsupported devices.
  }
}

export function mountLoginBackground(screen: HTMLElement): () => void {
  const old = screen.querySelector(".login-backdrop");
  if (old) throw new Error("Login background is already mounted");
  const stage = document.createElement("div"); stage.className = "login-backdrop";
  stage.setAttribute("aria-hidden", "true");
  const portal = document.createElement("canvas"); portal.className = "login-portal-canvas";
  const embers = document.createElement("canvas"); embers.className = "login-embers-canvas";
  stage.append(portal, embers); screen.prepend(stage);
  const toggle = document.createElement("button"); toggle.type = "button";
  toggle.className = "login-motion-toggle"; toggle.setAttribute("aria-pressed", "false");
  screen.querySelector(".login-shell")?.append(toggle);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let pass: PortalPass | null = null;
  const ctx = embers.getContext("2d");
  let width = 1, height = 1, ratio = 1, time = 0, previous = 0, rendered = 0, raf = 0;
  let userPaused = reduced.matches, disposed = false, lost = false, visible = true;
  let initialized = false;
  const particles = Array.from({ length: 60 }, (_, i) => ({
    phase: ((i*37)%61)/61, side: i%2, seed: ((i*71)%97)/97, spread: ((i*53)%89)/89,
  }));
  const motes = Array.from({ length: 24 }, (_, i) => ({
    phase: ((i*29)%41)/41, side: i%2 ? 1 : -1, seed: ((i*67)%83)/83, spread: ((i*31)%53)/53,
  }));
  let sprites: { warm: HTMLCanvasElement; cool: HTMLCanvasElement } | null = null;
  const glowSprite = (stops: Array<[number, string]>): HTMLCanvasElement => {
    const sprite = document.createElement("canvas"); sprite.width = sprite.height = 32;
    const g = sprite.getContext("2d");
    if (g) {
      const fill = g.createRadialGradient(16,16,0,16,16,16);
      for (const [at, stop] of stops) fill.addColorStop(at, stop);
      g.fillStyle = fill; g.fillRect(0,0,32,32);
    }
    return sprite;
  };
  const resize = (): void => {
    width = stage.clientWidth; height = stage.clientHeight;
    if (!width || !height) return;
    const mobile = width < 900;
    // No full-DPR offscreen buffer: bounded pixels and 30 updates/s.
    ratio = Math.min(1, (mobile ? 850 : 1280)/width, (mobile ? 850 : 720)/height);
    portal.width = embers.width = Math.max(1, Math.round(width*ratio));
    portal.height = embers.height = Math.max(1, Math.round(height*ratio));
    stage.dataset.buffer = `${portal.width}x${portal.height}`;
  };
  const draw = (): void => {
    if (!width || !height) return;
    pass?.draw(time, width, height);
    if (!ctx) return;
    ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,width,height);
    sprites ??= {
      warm: glowSprite([[0,"rgba(255,246,214,1)"],[.18,"rgba(255,190,90,.85)"],[.45,"rgba(255,110,30,.25)"],[1,"rgba(255,60,10,0)"]]),
      cool: glowSprite([[0,"rgba(240,248,255,1)"],[.2,"rgba(150,190,255,.8)"],[.5,"rgba(110,120,255,.22)"],[1,"rgba(90,80,255,0)"]]),
    };
    const scale = Math.max(width/1672,height/941), w=1672*scale,h=941*scale;
    const ox=(width-w)*.5,oy=(height-h)*.5;
    ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
    const mobile=width<900;
    // Embers: eased rise with turbulent sway, cooling from white-gold to red; the tail is the recent path.
    const ember=(particle: typeof particles[number], age: number): [number, number] => {
      const rise=h*(.1+particle.seed*.24)*(1-(1-age)*(1-age));
      const sway=Math.sin(age*5.3+particle.seed*17)*w*.011*age+Math.sin(age*13+particle.spread*9)*w*.003+(particle.spread-.5)*w*.045*age;
      return [ox+w*(particle.side===0?.228:.771)+(particle.spread-.5)*w*.04+sway, oy+h*.772-rise];
    };
    for (let i=0; i<(mobile?28:60); i++) {
      const particle=particles[i]!;
      const age=(particle.phase+time/(2.4+particle.seed*2.6))%1;
      const [x,y]=ember(particle,age);
      if (x<-40 || x>width+40) continue;
      const [tx,ty]=ember(particle,Math.max(0,age-.035));
      const fade=Math.min(1,age*10)*Math.pow(1-age,1.4), heat=1-age;
      const size=(.7+particle.seed*1.3)*scale*(1-age*.45), glow=size*8;
      ctx.strokeStyle=`rgba(255,${Math.round(90+150*heat*heat)},${Math.round(30+150*heat**4)},${(fade*.7).toFixed(3)})`;
      ctx.lineWidth=size; ctx.beginPath(); ctx.moveTo(tx,ty); ctx.lineTo(x,y); ctx.stroke();
      ctx.globalAlpha=fade*.65; ctx.drawImage(sprites.warm,x-glow/2,y-glow/2,glow,glow); ctx.globalAlpha=1;
    }
    // Astral motes: rising out of the threshold mist, or drifting up just inside the arch.
    for (let i=0; i<(mobile?16:24); i++) {
      const mote=motes[i]!;
      const age=(mote.phase+time/(6+mote.seed*6))%1;
      const sway=Math.sin(age*6.3+mote.seed*20)*w*.005;
      let x: number, y: number;
      if (i%3===0) {
        x=ox+w*(.5+mote.side*mote.spread*.1)+sway; y=oy+h*(.85-(.06+mote.seed*.16)*age);
      } else {
        const angle=Math.PI*.5+mote.side*(.3+mote.spread*1.05), reach=.88-mote.seed*.14;
        x=ox+w*(.5+Math.cos(angle)*.136*reach)+sway; y=oy+h*(.477+Math.sin(angle)*.374*reach-(.05+mote.seed*.12)*age);
      }
      const twinkle=.55+.45*Math.sin(time*(3+mote.seed*4)+mote.spread*30);
      const glow=(.8+mote.seed*1.2)*scale*9;
      ctx.globalAlpha=Math.sin(age*Math.PI)*twinkle*.75; ctx.drawImage(sprites.cool,x-glow/2,y-glow/2,glow,glow);
    }
    ctx.globalAlpha=1; ctx.globalCompositeOperation="source-over";
  };
  const canRun = (): boolean => !disposed && !screen.hidden && screen.isConnected &&
    document.visibilityState !== "hidden" && visible && !userPaused;
  const frame = (now: number): void => {
    raf = 0;
    if (!canRun()) { previous=0; return; }
    if (!rendered || now-rendered >= 1000/30-1) {
      time += previous ? Math.min(.1,(now-previous)/1000) : 0;
      previous=rendered=now; draw();
      stage.dataset.time=time.toFixed(2);
    }
    raf=requestAnimationFrame(frame);
  };
  const sync = (): void => {
    if (disposed) return;
    const active=canRun();
    if (active && !initialized) { initialized=true; pass=createPortal(portal); }
    stage.dataset.renderer=lost?"context-lost":pass?"webgl2":"static";
    stage.dataset.motion=active?"running":"paused";
    const th=screen.lang === "th";
    toggle.textContent=userPaused?(th?"เปิดเอฟเฟกต์":"Play effects"):(th?"หยุดเอฟเฟกต์":"Pause effects");
    toggle.title=reduced.matches?(th?"อุปกรณ์ตั้งค่าลดการเคลื่อนไหวไว้ คุณเลือกเปิดเอฟเฟกต์ได้":"Your device requests reduced motion. You may choose to play effects."):"";
    toggle.setAttribute("aria-pressed",String(userPaused));
    if (active && !raf) { previous=rendered=0; raf=requestAnimationFrame(frame); }
    if (!active) { cancelAnimationFrame(raf); raf=0; previous=rendered=0; }
  };
  const click = (): void => { userPaused=!userPaused; sync(); };
  const preference = (): void => { userPaused=reduced.matches; sync(); };
  const contextLost = (event: Event): void => { event.preventDefault(); lost=true; pass=null; sync(); };
  const restored = (): void => { lost=false; pass=createPortal(portal); sync(); };
  const pageHide = (): void => { cancelAnimationFrame(raf); raf=0; previous=rendered=0; };
  const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(stage);
  const observer = new MutationObserver(sync); observer.observe(screen,{ attributes:true,attributeFilter:["hidden","lang"] });
  const intersection = new IntersectionObserver(entries => { visible=entries[0]?.isIntersecting ?? false; sync(); });
  intersection.observe(screen);
  portal.addEventListener("webglcontextlost",contextLost); portal.addEventListener("webglcontextrestored",restored);
  toggle.addEventListener("click",click); reduced.addEventListener("change",preference);
  document.addEventListener("visibilitychange",sync);
  window.addEventListener("pagehide",pageHide); window.addEventListener("pageshow",sync);
  resize(); sync();
  return () => {
    if (disposed) return;
    disposed=true; cancelAnimationFrame(raf);
    resizeObserver.disconnect(); observer.disconnect(); intersection.disconnect();
    reduced.removeEventListener("change",preference); document.removeEventListener("visibilitychange",sync);
    window.removeEventListener("pagehide",pageHide); window.removeEventListener("pageshow",sync);
    portal.removeEventListener("webglcontextlost",contextLost); portal.removeEventListener("webglcontextrestored",restored);
    toggle.removeEventListener("click",click); pass?.dispose();
    if (initialized) portal.getContext("webgl2")?.getExtension("WEBGL_lose_context")?.loseContext();
    portal.width=portal.height=embers.width=embers.height=1;
    stage.remove(); toggle.remove();
  };
}
