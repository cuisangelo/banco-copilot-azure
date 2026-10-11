const integer = new Intl.NumberFormat("es-CL");
const usd = new Intl.NumberFormat("es-CL", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 6,
});

export const formatInt = (n: number) => integer.format(n);
// Summing float costs drifts in the last digits; round to the displayed precision.
export const formatUsd = (n: number) => usd.format(Math.round(n * 1e6) / 1e6);
export const formatTime = (iso: string) =>
  new Date(iso).toLocaleString("es-CL", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
