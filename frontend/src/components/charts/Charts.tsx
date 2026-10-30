import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDate, formatPercent } from "../../lib/format";
import type { AnalyticsOverview, TopicStat } from "../../lib/types";

const axis = { stroke: "var(--fg-muted)", fontSize: 12, tickLine: false, axisLine: false } as const;
const tooltipStyle = {
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    color: "var(--fg)",
    fontSize: 13,
  },
  labelStyle: { color: "var(--fg)", fontWeight: 600 },
};

export function ScoreTrendChart({ data }: { data: AnalyticsOverview["trend"] }) {
  const points = data.map((p, i) => ({ ...p, index: i + 1, label: formatDate(p.submitted_at) }));
  return (
    <div className="h-64" role="img" aria-label={`Score trend over ${data.length} attempts`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="index" {...axis} />
          <YAxis domain={[(min: number) => Math.min(0, Math.floor(min / 10) * 10), 100]} {...axis} tickFormatter={(v: number) => `${v}%`} />
          <Tooltip
            {...tooltipStyle}
            formatter={(value) => [formatPercent(Number(value)), "Score"]}
            labelFormatter={(_, payload) => {
              const item = payload?.[0]?.payload as (typeof points)[number] | undefined;
              return item ? `${item.test_title} · ${item.label}` : "";
            }}
          />
          <Line type="monotone" dataKey="percentage" stroke="#6366f1" strokeWidth={2.5} dot={{ r: 3.5, fill: "#6366f1" }} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const barColor = (accuracy: number | null) =>
  accuracy === null ? "#94a3b8" : accuracy >= 75 ? "#10b981" : accuracy >= 40 ? "#f59e0b" : "#f43f5e";

export function TopicAccuracyChart({ topics }: { topics: TopicStat[] }) {
  const data = topics.slice(0, 12).map((t) => ({ ...t, value: t.accuracy ?? 0 }));
  return (
    <div style={{ height: Math.max(160, data.length * 40) }} role="img" aria-label="Accuracy by topic">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...axis} tickFormatter={(v: number) => `${v}%`} />
          <YAxis type="category" dataKey="topic" width={120} {...axis} tickFormatter={(v: string) => (v.length > 16 ? `${v.slice(0, 15)}…` : v)} />
          <Tooltip
            {...tooltipStyle}
            cursor={{ fill: "var(--surface-2)" }}
            formatter={(_value, _name, item) => {
              const t = item.payload as TopicStat;
              return [`${formatPercent(t.accuracy)} (${t.correct}/${t.correct + t.incorrect} attempted, ${t.unanswered} skipped)`, "Accuracy"];
            }}
          />
          <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={20}>
            {data.map((t) => (
              <Cell key={t.topic} fill={barColor(t.accuracy)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
