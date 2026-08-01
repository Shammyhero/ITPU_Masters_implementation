import data from "@/data/aist.json";
import Detectability, { type DetectabilityData } from "@/components/Detectability";
import Headline, { type Stat } from "@/components/Headline";
import Inversion, { type InversionData } from "@/components/Inversion";
import Probe, { type ProbeData } from "@/components/Probe";
import ProbeLive from "@/components/ProbeLive";
import Stress, { type StressData } from "@/components/Stress";

export default function Page() {
  return (
    <main>
      <h1>Detectability determines danger</h1>
      <p className="lede">
        An autonomous agent given degraded data does not usually crash or
        refuse. It answers confidently and wrongly. This is what that looks
        like, measured — and what a pipeline score can tell you{" "}
        <em>before</em> you deploy an agent on it.
      </p>
      <p className="src" style={{ marginTop: "1rem" }}>
        Every figure below is exported from {data.generated_from.runs} benchmark
        runs. This page makes no model calls and needs no API key.
      </p>

      <div style={{ marginTop: "2.5rem" }}>
        <Headline stats={data.headline as Stat[]} />
      </div>

      <Stress
        data={data.stress as StressData}
        weights={data.probe.weights as Record<string, number>}
      />
      <Detectability data={data.detectability as unknown as DetectabilityData} />
      <Inversion data={data.inversion as InversionData} />
      <Probe data={data.probe as ProbeData} />
      <ProbeLive weights={data.probe.weights as Record<string, number>} />

      <footer>
        <p>
          <b>AIST</b> — Agentic Infrastructure Stress Test. Companion to{" "}
          <em>Detectability Determines Danger: How Data Infrastructure Faults
          Cause Silent Failure in Agentic AI Systems</em>, Shamsiddin Khamidov,
          IT Park University, 2026.
        </p>
        <p>
          Regenerate the data with <span className="mono">npm run data</span>.
          The benchmark, the fault injector, and the{" "}
          <span className="mono">airs probe</span> scorer are in the same
          repository.
        </p>
      </footer>
    </main>
  );
}
