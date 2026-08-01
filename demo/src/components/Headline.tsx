export type Stat = {
  value: string;
  label: string;
  caption: string;
  source: string;
  emphasis?: boolean;
};

export default function Headline({ stats }: { stats: Stat[] }) {
  return (
    <div className="grid stats">
      {stats.map((s) => (
        <div key={s.label} className={`panel stat${s.emphasis ? " em" : ""}`}>
          <div className="v">{s.value}</div>
          <div className="l">{s.label}</div>
          <div className="c">{s.caption}</div>
          <div className="src">{s.source}</div>
        </div>
      ))}
    </div>
  );
}
