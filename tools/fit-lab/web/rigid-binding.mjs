// skinIndex is already remapped to the shared body skeleton. Call per mesh, never per item.
export function dominantJoint(indices, weights) {
  const totals = new Map();
  for (let i = 0; i < indices.count; i++) for (let j = 0; j < 4; j++) {
    const weight = weights.getComponent(i, j);
    if (weight <= 0) continue;
    const joint = indices.getComponent(i, j);
    totals.set(joint, (totals.get(joint) || 0) + weight);
  }
  return [...totals].sort((a, b) => b[1] - a[1])[0]?.[0];
}
