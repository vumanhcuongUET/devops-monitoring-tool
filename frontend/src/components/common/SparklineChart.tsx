import type { MetricSeries } from '../../types';

export function SparklineChart({
  data,
  color = 'var(--color-accent)',
  height = 40,
}: {
  data: MetricSeries[];
  color?: string;
  height?: number;
}) {
  if (!data.length) return <div style={{ height }} />;

  const values = data.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const width = 100;
  const step = width / Math.max(data.length - 1, 1);
  const points = values
    .map((v, i) => {
      const x = i * step;
      const y = range ? height - ((v - min) / range) * height : height / 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
