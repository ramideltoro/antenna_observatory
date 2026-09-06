'use client';

import { memo, useId, useMemo, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import type { HistoryPoint } from '@/lib/telemetry';

export type Series = { key: string; label: string; color: string };
export type ChartProps = {
  points: HistoryPoint[];
  series: Series[];
  unit?: string;
  height?: number;
};

const number = (value: number) =>
  value.toLocaleString('en-US', { maximumFractionDigits: 2 });
const stamp = (value: number, seconds = false) =>
  new Date(value * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    ...(seconds ? { second: '2-digit' } : {}),
  });
function measurement(point: HistoryPoint, key: string): number | null {
  const value = key
    .split('.')
    .reduce<unknown>(
      (current, part) =>
        current !== null && typeof current === 'object'
          ? (current as Record<string, unknown>)[part]
          : undefined,
      point,
    );
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function ReadingTooltip({
  active,
  payload,
  label,
  unit,
}: TooltipContentProps & { unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="reading-tooltip">
      <time>
        {typeof label === 'number'
          ? new Date(label * 1000).toLocaleString()
          : label}
      </time>
      {payload.map((item) => (
        <div key={String(item.dataKey)}>
          <span>
            <i style={{ background: item.color }} />
            {item.name}
          </span>
          <strong>
            {typeof item.value === 'number' ? number(item.value) : '—'}
          </strong>
        </div>
      ))}
      <small>{unit}</small>
    </div>
  );
}

function SignalChart({
  points,
  series,
  unit = 'messages / second',
  height = 224,
}: ChartProps) {
  const gradient = useId().replaceAll(':', '');
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  // Parent telemetry refreshes every two seconds; only rebuild the chart for new history/series.
  const seriesKeys = series.map((item) => item.key).join('|');
  const chart = useMemo(() => {
    const keys = seriesKeys.split('|');
    const rows: Record<string, number | null>[] = [];
    const first = points[0]?.ts ?? 0;
    const last = points.at(-1)?.ts ?? first;
    const gap = Math.max(
      45,
      ((last - first) / Math.max(1, points.length - 1)) * 3,
    );
    let minimum = 0;
    let populated = 0;
    points.forEach((point, index) => {
      if (index > 0 && point.ts - points[index - 1].ts > gap) {
        rows.push({
          ts: points[index - 1].ts + 1,
          ...Object.fromEntries(
            keys.map((_, column) => [`value${column}`, null]),
          ),
        });
      }
      const row: Record<string, number | null> = { ts: point.ts };
      keys.forEach((key, column) => {
        const value = measurement(point, key);
        row[`value${column}`] = value;
        if (value !== null) {
          minimum = Math.min(minimum, value);
          populated += 1;
        }
      });
      rows.push(row);
    });
    return { rows, minimum, populated, first, last };
  }, [points, seriesKeys]);
  const toggle = (key: string) =>
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else if (series.filter((item) => !next.has(item.key)).length > 1)
        next.add(key);
      return next;
    });

  return (
    <figure
      className="trend"
      aria-label={`${series.map((s) => s.label).join(' and ')} in ${unit}`}
    >
      <div className="chart-meta">
        <span>{unit}</span>
        <span>Tap chart to inspect</span>
      </div>
      <div className="chart-canvas" style={{ height }}>
        {chart.populated && points.length > 1 ? (
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={0}
            initialDimension={{ width: 560, height }}
            debounce={60}
          >
            <ComposedChart
              data={chart.rows}
              margin={{ top: 12, right: 8, left: -10, bottom: 0 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={series[0]?.color}
                    stopOpacity={0.25}
                  />
                  <stop
                    offset="100%"
                    stopColor={series[0]?.color}
                    stopOpacity={0.01}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                vertical={false}
                stroke="var(--border)"
                strokeDasharray="3 6"
              />
              <XAxis
                dataKey="ts"
                type="number"
                domain={['dataMin', 'dataMax']}
                scale="time"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                minTickGap={48}
                tickMargin={12}
                height={36}
                tickFormatter={(value: number) =>
                  chart.last - chart.first > 86400
                    ? new Date(value * 1000).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      })
                    : stamp(value)
                }
              />
              <YAxis
                width={50}
                axisLine={false}
                tickLine={false}
                tickCount={4}
                domain={[
                  chart.minimum < 0 ? Math.floor(chart.minimum / 5) * 5 : 0,
                  'auto',
                ]}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                tickFormatter={(value: number) =>
                  Math.abs(value) >= 1000
                    ? `${number(value / 1000)}k`
                    : number(value)
                }
              />
              <Tooltip
                content={(props) => <ReadingTooltip {...props} unit={unit} />}
                isAnimationActive={false}
                cursor={{ stroke: 'var(--primary)', strokeDasharray: '3 4' }}
              />
              {series.map((item, index) =>
                index === 0 && chart.minimum >= 0 ? (
                  <Area
                    key={item.key}
                    dataKey={`value${index}`}
                    name={item.label}
                    type="linear"
                    stroke={item.color}
                    strokeWidth={2}
                    fill={`url(#${gradient})`}
                    fillOpacity={1}
                    hide={hidden.has(item.key)}
                    connectNulls={false}
                    dot={false}
                    activeDot={{
                      r: 5,
                      stroke: 'var(--background)',
                      strokeWidth: 2,
                    }}
                    isAnimationActive={false}
                  />
                ) : (
                  <Line
                    key={item.key}
                    dataKey={`value${index}`}
                    name={item.label}
                    type="linear"
                    stroke={item.color}
                    strokeWidth={2}
                    hide={hidden.has(item.key)}
                    connectNulls={false}
                    dot={false}
                    activeDot={{
                      r: 5,
                      stroke: 'var(--background)',
                      strokeWidth: 2,
                    }}
                    isAnimationActive={false}
                  />
                ),
              )}
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="chart-empty">
            {points.length
              ? 'Collecting more measurements…'
              : 'History begins when the collector is running.'}
          </div>
        )}
      </div>
      <figcaption className="chart-legend">
        {series.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => toggle(item.key)}
            aria-pressed={!hidden.has(item.key)}
            aria-label={`${item.label} series`}
          >
            <i style={{ background: item.color }} />
            {item.label}
          </button>
        ))}
      </figcaption>
    </figure>
  );
}

export default memo(
  SignalChart,
  (previous, next) =>
    previous.points === next.points &&
    previous.unit === next.unit &&
    previous.height === next.height &&
    previous.series.length === next.series.length &&
    previous.series.every(
      (series, index) =>
        series.key === next.series[index].key &&
        series.label === next.series[index].label &&
        series.color === next.series[index].color,
    ),
);
