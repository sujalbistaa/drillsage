/** Display formatting. Values arrive in SI from the API; conversion happens only here. */

const INT = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const ONE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export function int(value: number): string {
  return INT.format(value);
}

export function oneDecimal(value: number): string {
  return ONE.format(value);
}

export function metres(value: number | null | undefined): string {
  return value == null ? "n/a" : `${INT.format(value)} m`;
}

export function hours(value: number): string {
  if (value === 0) return "0 h";
  return value < 10 ? `${ONE.format(value)} h` : `${INT.format(value)} h`;
}

/** Hole diameter in inches, the unit every driller speaks (8½", 12¼", 17½"). */
export function holeInches(diameterM: number | null | undefined): string | null {
  if (diameterM == null) return null;
  const inches = diameterM / 0.0254;
  const whole = Math.floor(inches + 1e-6);
  const fraction = inches - whole;
  const glyphs: [number, string][] = [
    [0, ""],
    [0.25, "¼"],
    [0.375, "⅜"],
    [0.5, "½"],
    [0.75, "¾"],
    [1, ""],
  ];
  const best = glyphs.reduce((a, b) =>
    Math.abs(b[0] - fraction) < Math.abs(a[0] - fraction) ? b : a,
  );
  const base = best[0] === 1 ? whole + 1 : whole;
  return `${base}${best[1]}″`;
}

export function density(gcc: number | null | undefined): string | null {
  return gcc == null ? null : `${gcc.toFixed(2)} sg`;
}

const DAY = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function day(iso: string): string {
  return DAY.format(new Date(iso)).toUpperCase();
}

export function year(iso: string): number {
  return new Date(iso).getUTCFullYear();
}
