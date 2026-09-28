/** Plan-view projection of UTM coordinates into an SVG viewport (north up, equal scale). */
export interface Bounds {
  minE: number;
  maxE: number;
  minN: number;
  maxN: number;
}

export function boundsOf(points: Iterable<readonly [number, number]>, padM = 150): Bounds {
  let minE = Infinity;
  let maxE = -Infinity;
  let minN = Infinity;
  let maxN = -Infinity;
  for (const [e, n] of points) {
    minE = Math.min(minE, e);
    maxE = Math.max(maxE, e);
    minN = Math.min(minN, n);
    maxN = Math.max(maxN, n);
  }
  if (!Number.isFinite(minE)) return { minE: 0, maxE: 1, minN: 0, maxN: 1 };
  return { minE: minE - padM, maxE: maxE + padM, minN: minN - padM, maxN: maxN + padM };
}

export interface Projection {
  width: number;
  height: number;
  /** Metres per SVG unit. */
  scale: number;
  x(e: number): number;
  y(n: number): number;
}

export function project(bounds: Bounds, width: number): Projection {
  const spanE = bounds.maxE - bounds.minE;
  const spanN = bounds.maxN - bounds.minN;
  const scale = spanE / width;
  const height = spanN / scale;
  return {
    width,
    height,
    scale,
    x: (e) => (e - bounds.minE) / scale,
    y: (n) => (bounds.maxN - n) / scale,
  };
}

/** A round scale-bar length (1, 2 or 5 × 10^k metres) close to `targetM`. */
export function niceLength(targetM: number): number {
  const power = 10 ** Math.floor(Math.log10(targetM));
  const steps = [1, 2, 5, 10];
  return power * (steps.find((s) => s * power >= targetM) ?? 10);
}

/** Web Mercator pixel coordinates of a WGS84 point at `zoom` (256-pixel tiles). */
export function mercatorPx(latDeg: number, lonDeg: number, zoom: number): [number, number] {
  const size = 256 * 2 ** zoom;
  const lat = (latDeg * Math.PI) / 180;
  const x = ((lonDeg + 180) / 360) * size;
  const y = ((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2) * size;
  return [x, y];
}
