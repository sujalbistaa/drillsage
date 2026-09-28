/**
 * Presentation of the canonical hazard taxonomy (the API's `HazardType`).
 * Colours are CSS variables from globals.css so both themes stay in sync.
 */
export interface HazardMeta {
  code: string;
  label: string;
  short: string;
  color: string;
  geological: boolean;
}

export const HAZARDS = {
  LOST_CIRCULATION: {
    code: "LC",
    label: "Lost circulation",
    short: "Losses",
    color: "var(--hz-lc)",
    geological: true,
  },
  WELL_CONTROL: {
    code: "WC",
    label: "Well control",
    short: "Kick / gas",
    color: "var(--hz-wc)",
    geological: true,
  },
  STUCK_PIPE: {
    code: "SP",
    label: "Stuck pipe",
    short: "Stuck",
    color: "var(--hz-sp)",
    geological: true,
  },
  TIGHT_HOLE: {
    code: "TH",
    label: "Tight hole",
    short: "Tight",
    color: "var(--hz-th)",
    geological: true,
  },
  WELLBORE_INSTABILITY: {
    code: "WI",
    label: "Wellbore instability",
    short: "Unstable",
    color: "var(--hz-wi)",
    geological: true,
  },
  SHALLOW_GAS_H2S: {
    code: "GS",
    label: "Shallow gas / H₂S",
    short: "Gas / H₂S",
    color: "var(--hz-gs)",
    geological: true,
  },
  CEMENTING: {
    code: "CM",
    label: "Cementing",
    short: "Cement",
    color: "var(--hz-cm)",
    geological: false,
  },
  CASING_RUNNING: {
    code: "CS",
    label: "Casing running",
    short: "Casing",
    color: "var(--hz-cs)",
    geological: false,
  },
  DIRECTIONAL: {
    code: "DD",
    label: "Directional",
    short: "Directional",
    color: "var(--hz-dd)",
    geological: false,
  },
  EQUIPMENT_FAILURE: {
    code: "EQ",
    label: "Equipment failure",
    short: "Equipment",
    color: "var(--hz-eq)",
    geological: false,
  },
  FISHING_JUNK: {
    code: "FJ",
    label: "Fishing / junk",
    short: "Fishing",
    color: "var(--hz-fj)",
    geological: false,
  },
  WAITING: {
    code: "WT",
    label: "Waiting",
    short: "Waiting",
    color: "var(--hz-wt)",
    geological: false,
  },
} as const satisfies Record<string, HazardMeta>;

export type HazardKey = keyof typeof HAZARDS;

export const HAZARD_KEYS = Object.keys(HAZARDS) as HazardKey[];
export const GEOLOGICAL_KEYS = HAZARD_KEYS.filter((k) => HAZARDS[k].geological);

const UNKNOWN: HazardMeta = {
  code: "??",
  label: "Unclassified",
  short: "Other",
  color: "var(--muted-foreground)",
  geological: false,
};

export function isHazardKey(value: string | undefined | null): value is HazardKey {
  return value != null && Object.hasOwn(HAZARDS, value);
}

export function hazardMeta(hazard: string): HazardMeta {
  return isHazardKey(hazard) ? HAZARDS[hazard] : UNKNOWN;
}

export const SEVERITY_LABELS = ["", "Minor", "Interrupted ops", "Lost a day", "Major"] as const;
