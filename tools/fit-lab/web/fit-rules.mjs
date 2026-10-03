export const storedDirection = direction => direction <= 4 ? direction : 8 - direction;
function compareKeys(a,b) {
  const left=Array.from(a, c=>c.codePointAt(0)), right=Array.from(b, c=>c.codePointAt(0));
  for(let i=0;i<Math.min(left.length,right.length);i++) if(left[i]!==right[i]) return left[i]-right[i];
  return left.length-right.length;
}
export function resolveFit(document, mapping, item, action = null, direction = null) {
  const base = {...mapping, ...(document.parts?.[item.part] || {})};
  const result = {offset: [...(base.offset || [0,0,0])], rotate: [...(base.rotate || [0,0,0])],
    scale: base.scale ?? 1, depth_scale: base.depth_scale ?? 1, bind: base.bind || 'skinned',
    hide_body: structuredClone(base.hide_body || {enabled:true, outward:.02, inward:.01}),
    occlusion: base.occlusion || (['back','quiver'].includes(item.slot) ? 'body' : 'clothing')};
  result.sides = structuredClone(document.items?.[item.id]?.sides || {});
  result.offset = result.offset.map((v,i) => v + (document.items?.[item.id]?.offset?.[i] || 0));
  const ranks = {pack:0, slot:1, group:2, item:3};
  const rules = [...(document.corrections || [])].sort((a,b) => ranks[a.target]-ranks[b.target] ||
    (('action' in a)+('direction' in a))-(('action' in b)+('direction' in b)) ||
    ('direction' in a)-('direction' in b) || compareKeys(a.key || '',b.key || ''));
  for (const rule of rules) {
    if (rule.target === 'slot' && rule.key !== item.slot) continue;
    if (rule.target === 'item' && rule.key !== item.id) continue;
    if (rule.target === 'group' && !document.groups?.[rule.key]?.includes(item.id)) continue;
    if ('action' in rule && rule.action !== action) continue;
    if ('direction' in rule && (direction === null || rule.direction !== storedDirection(direction))) continue;
    for (const field of ['offset','rotate']) result[field] = result[field].map((v,i) => v + (rule.fit[field]?.[i] || 0));
    result.scale *= rule.fit.scale ?? 1;
    result.depth_scale *= rule.fit.depth_scale ?? 1;
    if (rule.fit.occlusion) result.occlusion = rule.fit.occlusion;
  }
  return result;
}
