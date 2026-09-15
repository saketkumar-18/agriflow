// Lightweight hand-rolled SVG charts. No chart library.
// Every chart renders an sr-only <table> fallback for screen readers.

"use client";

import { useId } from "react";
import { useI18n } from "@/lib/i18n";
import { fmtNumber } from "@/lib/format";

const W = 340;
const H = 140;
const PAD = { top: 10, right: 8, bottom: 22, left: 30 };

interface Point {
  label: string;
  value: number | null;
}

function scale(points: Point[], minOverride?: number, maxOverride?: number) {
  const values = points.map((p) => p.value).filter((v): v is number => v != null);
  const lo = minOverride ?? Math.min(...values, 0);
  const hi = maxOverride ?? Math.max(...values, 1);
  const span = hi - lo || 1;
  const x = (i: number) =>
    PAD.left + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (W - PAD.left - PAD.right));
  const y = (v: number) =>
    PAD.top + (1 - (v - lo) / span) * (H - PAD.top - PAD.bottom);
  return { lo, hi, x, y };
}

function SrTable({
  title,
  columns,
  rows,
}: {
  title: string;
  columns: string[];
  rows: (string | number)[][];
}) {
  return (
    <table className="sr-only">
      <caption>{title}</caption>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c} scope="col">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((cell, j) => (
              <td key={j}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AxisLabels({ points, x }: { points: Point[]; x: (i: number) => number }) {
  const step = Math.max(1, Math.ceil(points.length / 5));
  return (
    <>
      {points.map((p, i) =>
        i % step === 0 || i === points.length - 1 ? (
          <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize="8" fill="#64748b">
            {p.label}
          </text>
        ) : null,
      )}
    </>
  );
}

export function LineChart({
  title,
  points,
  color = "#0f766e",
  unit,
  minOverride,
  maxOverride,
}: {
  title: string;
  points: Point[];
  color?: string;
  unit?: string;
  minOverride?: number;
  maxOverride?: number;
}) {
  const id = useId();
  const { lo, hi, x, y } = scale(points, minOverride, maxOverride);
  const present = points.map((p, i) => ({ ...p, i })).filter((p) => p.value != null);
  const path = present
    .map((p, idx) => `${idx === 0 ? "M" : "L"}${x(p.i).toFixed(1)},${y(p.value as number).toFixed(1)}`)
    .join(" ");
  const yTicks = [lo, (lo + hi) / 2, hi];
  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={id}
        className="w-full"
        preserveAspectRatio="none"
      >
        <title id={id}>{title}</title>
        {yTicks.map((tv, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tv)} y2={y(tv)} stroke="#e2e8f0" strokeWidth={1} />
            <text x={PAD.left - 4} y={y(tv) + 3} textAnchor="end" fontSize="8" fill="#64748b">
              {fmtNumber(tv, 0)}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {present.map((p) => (
          <circle key={p.i} cx={x(p.i)} cy={y(p.value as number)} r={2.5} fill={color} />
        ))}
        <AxisLabels points={points} x={x} />
      </svg>
      <SrTable
        title={title}
        columns={["Day", `${title}${unit ? ` (${unit})` : ""}`]}
        rows={points.map((p) => [p.label, p.value == null ? "—" : fmtNumber(p.value)])}
      />
    </figure>
  );
}

export function BarChart({
  title,
  points,
  color = "#0284c7",
  unit,
  highlight,
}: {
  title: string;
  points: Point[];
  color?: string;
  unit?: string;
  highlight?: (p: Point, i: number) => string | null;
}) {
  const id = useId();
  const values = points.map((p) => p.value ?? 0);
  const hi = Math.max(...values, 1);
  const bw = (W - PAD.left - PAD.right) / Math.max(points.length, 1);
  const y = (v: number) => PAD.top + (1 - v / hi) * (H - PAD.top - PAD.bottom);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={id} className="w-full" preserveAspectRatio="none">
        <title id={id}>{title}</title>
        <line x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} stroke="#cbd5e1" />
        {[hi / 2, hi].map((tv, i) => (
          <text key={i} x={PAD.left - 4} y={y(tv) + 3} textAnchor="end" fontSize="8" fill="#64748b">
            {fmtNumber(tv, 0)}
          </text>
        ))}
        {points.map((p, i) => {
          const v = p.value ?? 0;
          if (v <= 0) return null;
          const fill = highlight?.(p, i) ?? color;
          return (
            <rect
              key={i}
              x={PAD.left + i * bw + bw * 0.15}
              y={y(v)}
              width={bw * 0.7}
              height={H - PAD.bottom - y(v)}
              rx={2}
              fill={fill}
            />
          );
        })}
        <AxisLabels points={points} x={(i) => PAD.left + i * bw + bw / 2} />
      </svg>
      <SrTable
        title={title}
        columns={["Day", `${title}${unit ? ` (${unit})` : ""}`]}
        rows={points.map((p) => [p.label, fmtNumber(p.value ?? 0)])}
      />
    </figure>
  );
}

export function MultiLineChart({
  title,
  series,
  unit,
}: {
  title: string;
  series: { name: string; color: string; points: Point[] }[];
  unit?: string;
}) {
  const id = useId();
  const all = series.flatMap((s) => s.points);
  const { lo, hi, x, y } = scale(all);
  const n = Math.max(...series.map((s) => s.points.length), 1);
  const labels = series[0]?.points ?? [];
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={id} className="w-full" preserveAspectRatio="none">
        <title id={id}>{title}</title>
        {[lo, (lo + hi) / 2, hi].map((tv, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tv)} y2={y(tv)} stroke="#e2e8f0" />
            <text x={PAD.left - 4} y={y(tv) + 3} textAnchor="end" fontSize="8" fill="#64748b">
              {fmtNumber(tv, 0)}
            </text>
          </g>
        ))}
        {series.map((s) => (
          <path
            key={s.name}
            d={s.points
              .map((p, i) => (p.value == null ? "" : `${i === 0 || s.points[i - 1]?.value == null ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`))
              .join(" ")}
            fill="none"
            stroke={s.color}
            strokeWidth={2.2}
            strokeLinejoin="round"
          />
        ))}
        <AxisLabels points={labels} x={x} />
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-xs text-slate-600">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </figcaption>
      <SrTable
        title={title}
        columns={["Day", ...series.map((s) => `${s.name}${unit ? ` (${unit})` : ""}`)]}
        rows={Array.from({ length: n }, (_, i) => [
          labels[i]?.label ?? "",
          ...series.map((s) => (s.points[i]?.value == null ? "—" : fmtNumber(s.points[i].value as number))),
        ])}
      />
    </figure>
  );
}

export function MinMaxChart({
  title,
  points,
}: {
  title: string;
  points: { label: string; min: number; max: number }[];
}) {
  const id = useId();
  const lo = Math.min(...points.map((p) => p.min), 0);
  const hi = Math.max(...points.map((p) => p.max), 1);
  const span = hi - lo || 1;
  const x = (i: number) => PAD.left + (i / Math.max(points.length - 1, 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - lo) / span) * (H - PAD.top - PAD.bottom);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={id} className="w-full" preserveAspectRatio="none">
        <title id={id}>{title}</title>
        {points.map((p, i) => (
          <line key={i} x1={x(i)} x2={x(i)} y1={y(p.min)} y2={y(p.max)} stroke="#f59e0b" strokeWidth={3} strokeLinecap="round" />
        ))}
        <AxisLabels points={points.map((p) => ({ label: p.label, value: p.max }))} x={x} />
      </svg>
      <SrTable
        title={title}
        columns={["Day", "Min °C", "Max °C"]}
        rows={points.map((p) => [p.label, fmtNumber(p.min, 0), fmtNumber(p.max, 0)])}
      />
    </figure>
  );
}

// ---------- The lazy-loaded field-history chart panel ----------

import type { HistoryResponse } from "@/lib/types";

export function FieldCharts({ history }: { history: HistoryResponse }) {
  const { t } = useI18n();
  const dayLabel = (iso: string) =>
    new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

  const moisture: Point[] = history.soil_moisture.map((p) => ({ label: dayLabel(p.t), value: p.value }));
  const rain: Point[] = history.rainfall_mm.map((p) => ({ label: dayLabel(p.day), value: p.value }));
  const irr: Point[] = history.irrigation_mm.map((p) => ({ label: dayLabel(p.day), value: p.value }));
  const temp = history.temperature_c.map((p) => ({ label: dayLabel(p.day), min: p.min, max: p.max }));
  const etLabels = history.et0_mm.map((p) => dayLabel(p.day));
  const et0: Point[] = history.et0_mm.map((p, i) => ({ label: etLabels[i], value: p.value }));
  const etc: Point[] = history.etc_mm.map((p, i) => ({ label: etLabels[i] ?? "", value: p.value }));

  const chartDefs: { title: string; node: React.ReactNode }[] = [
    {
      title: t("field.chartSoilMoisture"),
      node: moisture.length ? <LineChart title={t("field.chartSoilMoisture")} points={moisture} color="#0f766e" unit="%" maxOverride={100} /> : null,
    },
    {
      title: t("field.chartRainfall"),
      node: rain.length ? (
        <BarChart
          title={t("field.chartRainfall")}
          points={rain}
          unit="mm"
          highlight={(p, i) => (history.rainfall_mm[i]?.kind === "forecast" ? "#7dd3fc" : "#0284c7")}
        />
      ) : null,
    },
    {
      title: t("field.chartTemperature"),
      node: temp.length ? <MinMaxChart title={t("field.chartTemperature")} points={temp} /> : null,
    },
    {
      title: t("field.chartIrrigation"),
      node: irr.length ? <BarChart title={t("field.chartIrrigation")} points={irr} color="#65a30d" unit="mm" /> : null,
    },
    {
      title: t("field.chartEt"),
      node: et0.length ? (
        <MultiLineChart
          title={t("field.chartEt")}
          unit="mm"
          series={[
            { name: `ET₀ (${t("field.estimated")})`, color: "#94a3b8", points: et0 },
            { name: `ETc (${t("field.estimated")})`, color: "#b91c1c", points: etc },
          ]}
        />
      ) : null,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {chartDefs.map((c) => (
        <section key={c.title} aria-label={c.title} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">{c.title}</h3>
          {c.node ?? <p className="text-sm text-slate-500">{t("common.noData")}</p>}
        </section>
      ))}
    </div>
  );
}
