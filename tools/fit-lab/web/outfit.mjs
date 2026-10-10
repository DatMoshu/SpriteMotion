// Whole-outfit view: kept slots stay visible while another slot is edited. View state only, never a fit edit.
// Document: common/schemas/fit-lab-view.schema.json. Rules: tools/fit-lab/README.md, "Whole outfit while fitting one slot".
export const SCHEMA = 'spritemotion.fit-lab-view';

export function emptyOutfit() { return { schema: SCHEMA, schema_version: 1, show: true, measure_outfit: false, worn: {} }; }

// Accept a stored document, dropping slots or items the manifest no longer has. Anything unreadable is empty.
export function parseOutfit(raw, items) {
  const outfit = emptyOutfit();
  let doc; try { doc = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return outfit; }
  if (!doc || doc.schema !== SCHEMA || doc.schema_version !== 1) return outfit;
  outfit.show = doc.show !== false; outfit.measure_outfit = doc.measure_outfit === true;
  const slotOf = new Map(items.map(i => [i.id, i.slot]));
  for (const [slot, id] of Object.entries(doc.worn && typeof doc.worn === 'object' ? doc.worn : {}))
    if (typeof id === 'string' && slotOf.get(id) === slot) outfit.worn[slot] = id;
  return outfit;
}

export const isKept = (outfit, slot) => slot in outfit.worn;
export function keep(outfit, slot, id) { return { ...outfit, worn: { ...outfit.worn, [slot]: id } }; }
export function release(outfit, slot) { const worn = { ...outfit.worn }; delete worn[slot]; return { ...outfit, worn }; }
export function clearOutfit(outfit) { return { ...outfit, worn: {} }; }
// Selecting another item in a kept slot changes what that slot wears.
export function select(outfit, slot, id) { return isKept(outfit, slot) ? keep(outfit, slot, id) : outfit; }

// Families in manifest order, each with the slots it covers.
export function families(items) {
  const out = new Map();
  for (const i of items) { const f = i.family || i.id; if (!out.has(f)) out.set(f, new Set()); out.get(f).add(i.slot); }
  return [...out].map(([family, slots]) => ({ family, slots: slots.size }));
}
// Keep the family's item in every slot that has one; other slots stay as they were.
export function wearSet(outfit, family, items) {
  const worn = { ...outfit.worn }, set = new Set();
  for (const i of items) if ((i.family || i.id) === family && !set.has(i.slot)) { worn[i.slot] = i.id; set.add(i.slot); }
  return { ...outfit, worn };
}

// Item ids rendered next to the edited slot. The edited slot never adds a kept item.
export function keptIds(outfit, editedSlot) {
  if (!outfit.show) return [];
  return Object.entries(outfit.worn).filter(([slot]) => slot !== editedSlot).map(([, id]) => id);
}
// Kept items whose hidden faces count for body hiding and Measure slot.
export function measuredKept(outfit, editedSlot) { return outfit.measure_outfit ? keptIds(outfit, editedSlot) : []; }
