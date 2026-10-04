/** Stock Babylon sphere V is polar angle / 180; update(false) keeps canvas row 0 at zenith. */
export function skyPaletteStops(zenith, horizon) {
  const mix = amount => zenith.map((value, i) => value + (horizon[i] - value) * amount);
  return [
    { offset: 0, color: [...zenith] },
    { offset: .39, color: [...zenith] },
    { offset: .444, color: mix(.45) },
    { offset: .483, color: mix(.85) },
    { offset: .5, color: [...horizon] },
    { offset: 1, color: [...horizon] },
  ];
}
