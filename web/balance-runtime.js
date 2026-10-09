'use strict';
(() => {
  if(window.GameCreatorBalance)return;
  const adapters=new Map();
  function register(value){
    if(!value||typeof value.id!=='string'||!Number.isInteger(value.version)||value.version<1||typeof value.calculate!=='function')throw Error(HarnessText.raw("js.balance.runtime.invalid.balance.adapter"));
    adapters.set(value.id,value);
  }
  async function run(definition,scenarios){
    const adapter=adapters.get(definition.adapter);if(!adapter||adapter.version!==definition.adapter_version)throw Error(HarnessText.raw("js.balance.runtime.connect.the.matching.game.calculation.adapter"));
    if(!Array.isArray(scenarios)||scenarios.length<1||scenarios.length>20)throw Error(HarnessText.raw("runtime.balance.compare.scenarios"));
    const results=[];
    for(const scenario of scenarios){
      const input={};
      for(const parameter of definition.parameters){const value=scenario.inputs?.[parameter.key];if(!Number.isFinite(value)||value<parameter.min||value>parameter.max)throw Error(HarnessText.raw("js.balance.runtime.input.outside.allowed.range")+parameter.key);input[parameter.key]=value;}
      // Run the registered game function, never a formula sent by the dashboard.
      const output=await adapter.calculate(Object.freeze({...input})),filtered={};
      for(const metric of definition.outputs){const value=output?.[metric.key];if(!Number.isFinite(value))throw Error(HarnessText.raw("js.balance.runtime.calculation.must.return.a.finite.number")+metric.key);filtered[metric.key]=value;}
      results.push({name:scenario.name,inputs:input,outputs:filtered});
    }
    return results;
  }
  window.GameCreatorBalance={register,run,list:()=>[...adapters.values()].map(a=>({id:a.id,version:a.version}))};
})();
