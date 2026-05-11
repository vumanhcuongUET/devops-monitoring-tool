import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
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

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <YAxis domain={['dataMin', 'dataMax']} hide />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
