/** Number formatting — single module, locale-aware, human-readable. */

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const cf = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmtPrice = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "—" : nf.format(v);

export const fmtCompact = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "—" : compact.format(v);

export const fmtCurrency = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "—" : cf.format(v);

export const fmtPct = (v: number | null | undefined, signed = true): string => {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
};

export const fmtDelta = (v: number | null | undefined): string => {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${nf.format(v)}`;
};

export const fmtInt = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "—" : Math.round(v).toLocaleString("en-US");

export const pctClass = (v: number | null | undefined): string =>
  v == null ? "text-fg-2" : v > 0 ? "text-up" : v < 0 ? "text-down" : "text-fg-2";
