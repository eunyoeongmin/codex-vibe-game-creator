/* Reusable browser runtime; no dependency on the dashboard or its database. */
'use strict';
(() => {
  if (window.GameCreatorTimeline) return;
  const targets = new Map(); let running = null, serial = 0;
  const abortError = () => new DOMException(HarnessText.raw("js.timeline.player.playback.stopped"), 'AbortError');
  function wait(seconds, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) return reject(abortError());
      const abort = () => { clearTimeout(timer); reject(abortError()); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, seconds * 1000);
      signal.addEventListener('abort', abort, {once: true});
    });
  }
  function overlay() {
    const box = document.createElement('div');
    Object.assign(box.style, {position: 'fixed', inset: '0', pointerEvents: 'none', zIndex: '2147483645', display: 'grid', placeItems: 'center'});
    document.body.append(box); return box;
  }
  function cancellable(promise, signal, timeout = 10000) {
    return new Promise((resolve,reject)=>{
      const abort=()=>finish(abortError()), timer=setTimeout(()=>finish(new Error(HarnessText.raw("js.timeline.player.media.or.target.did.not.respond.in.time"))),timeout);
      function finish(error,value){clearTimeout(timer);signal.removeEventListener('abort',abort);error?reject(error):resolve(value);}
      signal.addEventListener('abort',abort,{once:true});
      if(signal.aborted) return abort();
      Promise.resolve(promise).then(value=>finish(null,value),error=>finish(error));
    });
  }
  async function play(sequence, options = {}) {
    if (!sequence || !Array.isArray(sequence.steps)) throw new Error(HarnessText.raw("js.timeline.player.timeline.steps.are.required"));
    const request = ++serial; running?.control.abort();
    const previous = running; if (previous) await previous.finished;
    if(request!==serial) throw abortError();
    const control = new AbortController(), signal = control.signal, cleanup = [], undo = [];
    let done; const finished = new Promise(resolve => { done = resolve; });
    const instance = {control, finished}; running = instance;
    const outerAbort = () => control.abort(); options.signal?.addEventListener('abort', outerAbort, {once: true});
    if (options.signal?.aborted) control.abort();
    const baseURL = new URL(options.baseURL || './', window.location.href);
    let success = false;
    try {
      for (let index = 0; index < sequence.steps.length; index++) {
        const step = sequence.steps[index];
        if (!Number.isFinite(step.duration) || step.duration <= 0 || !Number.isFinite(step.delay) || step.delay < 0) throw new Error(HarnessText.raw("js.timeline.player.invalid.step.timing"));
        await wait(step.delay, signal); options.onStep?.({index, step, status: 'playing'});
        const local = [];
        try {
          const registered = targets.get(step.target);
          if (registered) {
            const restore = await cancellable(registered.run(step, {signal, preview: !!options.preview, baseURL}),signal,Math.max(10000,step.duration*1000+5000));
            if (typeof restore === 'function') undo.push(restore);
            if (signal.aborted) throw abortError();
          } else if (step.kind === 'move') {
            const target = document.querySelector('[data-timeline-target="'+CSS.escape(step.target)+'"]') || document.querySelector(step.target);
            if (!target) throw new Error(HarnessText.raw("js.timeline.player.movement.target.not.found") + step.target);
            const original = target.style.transform, base = getComputedStyle(target).transform;
            const final = (base === 'none' ? '' : base) + ` translate(${step.x}px, ${step.y}px)`;
            const animation = target.animate([{transform: base}, {transform: final}], {duration: step.duration * 1000, fill: 'forwards', easing: 'ease-in-out'});
            local.push(() => animation.cancel()); undo.push(() => { target.style.transform = original; });
            await wait(step.duration, signal); target.style.transform = final;
          } else if (step.kind === 'dialogue') {
            const box = overlay(), caption = document.createElement('div'); caption.textContent = step.text || '';
            Object.assign(caption.style, {alignSelf: 'end', margin: '5%', padding: '1em', background: '#10151fee', color: 'white', maxWidth: '85%', whiteSpace: 'pre-wrap', font: '20px/1.5 sans-serif', borderRadius: '10px'});
            box.append(caption); local.push(() => box.remove()); await wait(step.duration, signal);
          } else if (step.kind === 'sound') {
            const audio = new Audio(new URL(step.src, baseURL));
            local.push(() => { audio.pause(); audio.removeAttribute('src'); audio.load(); });
            await cancellable(audio.play(),signal); await wait(step.duration, signal);
          } else if (step.kind === 'image') {
            const box = overlay(), image = document.createElement('img'); image.src = new URL(step.src, baseURL); image.alt = '';
            Object.assign(image.style, {maxWidth: '90%', maxHeight: '90vh', objectFit: 'contain'});
            box.append(image); local.push(() => box.remove()); await cancellable(image.decode(),signal); await wait(step.duration, signal);
          } else if (step.kind === 'transition') {
            const box = overlay(); box.style.background = step.color;
            const animation = box.animate([{opacity: 0}, {opacity: 1, offset: .5}, {opacity: 0}], {duration: step.duration * 1000});
            local.push(() => { animation.cancel(); box.remove(); }); await wait(step.duration, signal);
          } else if (step.kind === 'wait') await wait(step.duration, signal);
          else throw new Error(HarnessText.raw("js.timeline.player.unknown.action") + step.kind);
        } finally { for (const dispose of local.reverse()) dispose(); }
        options.onStep?.({index, step, status: 'done'});
      }
      success = true;
    } finally {
      if (options.preview || !success) for (const restore of undo.reverse()) { try { await restore(); } catch (_) {} }
      for (const dispose of cleanup) dispose();
      options.signal?.removeEventListener('abort', outerAbort);
      if (running === instance) running = null; done();
    }
  }
  function stop() { serial++; running?.control.abort(); }
  window.GameCreatorTimeline = {
    play, stop,
    async load(url, options = {}) {
      const response = await fetch(url); if (!response.ok) throw new Error(HarnessText.raw("js.timeline.player.could.not.load.timeline"));
      return play(await response.json(), options);
    },
    registerTarget(id, label, run) {
      if (!id || typeof run !== 'function') throw new Error(HarnessText.raw("js.timeline.player.a.target.id.and.handler.are.required"));
      targets.set(id, {label, run}); return () => targets.delete(id);
    },
    targets() { return [...targets].map(([id, value]) => ({id, label: value.label})).concat([...document.querySelectorAll('[data-timeline-target]')].map(el=>({id:el.dataset.timelineTarget,label:el.dataset.timelineLabel||el.dataset.timelineTarget}))); }
  };
})();
