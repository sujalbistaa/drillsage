/** URL-safe identifiers for wellbore names like `15/9-F-1 C`. */
export function wellSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function findBySlug<T extends { name: string }>(
  items: readonly T[],
  slug: string,
): T | null {
  return items.find((item) => wellSlug(item.name) === slug) ?? null;
}

/** The short name drillers use on the rig floor: `F-1 C`, `19 BT2`. */
export function shortName(name: string): string {
  return name.replace(/^15\/9-/, "");
}
