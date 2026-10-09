'use strict';
(() => {
  const parentOrigin = document.currentScript?.dataset.parent;
  const buildFingerprint = document.currentScript?.dataset.fingerprint;
  if (!parentOrigin) return;
  window.addEventListener('creator-live-picked',event=>window.parent.postMessage({type:'creator-live-selection',id:event.detail.id},parentOrigin));
  window.addEventListener('message', async event => {
    if (event.origin !== parentOrigin || event.source !== window.parent || !['creator-live', 'creator-balance', 'creator-play', 'creator-state-request', 'creator-timeline-play', 'creator-timeline-stop', 'creator-timeline-targets'].includes(event.data?.type)) return;
    const nonce = event.data.nonce;
    if (typeof nonce !== 'string' || nonce.length > 80) return;
    if(event.data.type === 'creator-live') {
      try {
        const op=event.data.operation;
        if(!['info','start','stop','pick','cancel','select','pause','resume','capture'].includes(op))throw Error(HarnessText.raw('live.invalid_operation'));
        const result=await window.GameCreatorLive[op](event.data.target);
        if(op==='capture')result.build_fingerprint=buildFingerprint;
        window.parent.postMessage({type:'creator-live-result',nonce,result},parentOrigin);
      }catch(error){window.parent.postMessage({type:'creator-live-result',nonce,error:String(error.message)},parentOrigin);}
      return;
    }
    if(event.data.type === 'creator-balance') {
      try {
        if(JSON.stringify(event.data).length>200000)throw Error(HarnessText.raw("js.feedback.bridge.balance.request.too.large"));
        const result=await window.GameCreatorBalance.run(event.data.definition,event.data.scenarios);
        window.parent.postMessage({type:'creator-balance-result',nonce,result},parentOrigin);
      }catch(error){window.parent.postMessage({type:'creator-balance-result',nonce,error:String(error.message)},parentOrigin);}
      return;
    }
    if (event.data.type === 'creator-play') {
      try {
        let result; const op = event.data.operation;
        if (op === 'info') result = window.GameCreatorPlay?.info();
        else if (op === 'capture') result = await window.GameCreatorPlay.capture();
        else if (op === 'migrate') result = await window.GameCreatorPlay.migrate(event.data.snapshot);
        else if (op === 'restore') result = await window.GameCreatorPlay.restore(event.data.snapshot);
        else if (op === 'strings') result = window.GameCreatorStrings.issues();
        else if (op === 'language') { window.GameCreatorStrings.setLanguage(event.data.locale); result = window.GameCreatorStrings.issues(); }
        else throw new Error(HarnessText.raw("js.feedback.bridge.unknown.play.operation"));
        window.parent.postMessage({type:'creator-play-result', nonce, result}, parentOrigin);
      } catch(error) { window.parent.postMessage({type:'creator-play-result', nonce, error:String(error.message)}, parentOrigin); }
      return;
    }
    const reply = value => window.parent.postMessage({type: 'creator-timeline-event', nonce, ...value}, parentOrigin);
    if (event.data.type === 'creator-timeline-stop') { window.GameCreatorTimeline?.stop(); return; }
    if (event.data.type === 'creator-timeline-targets') { reply({status: 'targets', targets: window.GameCreatorTimeline?.targets() || []}); return; }
    if (event.data.type === 'creator-timeline-play') {
      try {
        if (!window.GameCreatorTimeline) throw new Error(HarnessText.raw("js.feedback.bridge.timeline.runtime.unavailable.reload.the.preview"));
        if (JSON.stringify(event.data.timeline).length > 500000) throw new Error(HarnessText.raw("js.feedback.bridge.timeline.too.large"));
        await window.GameCreatorTimeline.play(event.data.timeline, {preview: true, baseURL: new URL('/', location.href), onStep: item => reply({status: item.status, index: item.index})});
        reply({status: 'finished'});
      } catch (error) { reply({status: error.name === 'AbortError' ? 'stopped' : 'error', error: String(error.message)}); }
      return;
    }
    try {
      const state = typeof window.GameCreatorFeedback === 'function' ? await window.GameCreatorFeedback() : null;
      const encoded = JSON.stringify(state);
      if (encoded.length > 32000) throw new Error(HarnessText.raw("js.feedback.bridge.state.exceeds.kb"));
      window.parent.postMessage({type: 'creator-state', nonce, state: JSON.parse(encoded), at: new Date().toISOString()}, parentOrigin);
    } catch (_) {
      window.parent.postMessage({type: 'creator-state', nonce, state: null, at: null}, parentOrigin);
    }
  });
})();
