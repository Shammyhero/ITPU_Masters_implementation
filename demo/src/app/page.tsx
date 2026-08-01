import data from "@/data/aist.json";
import AskTheAgent from "@/components/AskTheAgent";
import Challenge, { type Case } from "@/components/Challenge";
import Inversion, { type InversionData } from "@/components/Inversion";
import Legibility, { type LegibilityData } from "@/components/Legibility";
import ProbeLive from "@/components/ProbeLive";
import Stress, { type StressData } from "@/components/Stress";

export default function Page() {
  const weights = data.probe.weights as Record<string, number>;
  return (
    <main>
      <header className="hero">
        <h1>Your agent is not going to tell you.</h1>
        <p className="lede">
          Give an autonomous agent degraded data and it rarely crashes, errors,
          or declines. It answers — fluently, confidently, and wrongly. This page
          lets you watch that happen on real data, work out why, and then measure
          the pipeline instead.
        </p>
        <p className="src">
          Every figure comes from {data.generated_from.runs} benchmark runs
          across four models. Nothing here calls a model or needs an API key.
        </p>
      </header>

      <Challenge cases={data.challenge as Case[]} />
      <Legibility data={data.legibility as LegibilityData} />
      <AskTheAgent />
      <ProbeLive weights={weights} />

      <hr className="rule" />
      <p className="explore-note">
        The rest is for readers who want to poke at the underlying data.
      </p>
      <Stress data={data.stress as StressData} weights={weights} />
      <Inversion data={data.inversion as InversionData} />

      <footer>
        <p>
          <b>AIST</b> — Agentic Infrastructure Stress Test. Companion to{" "}
          <em>
            Detectability Determines Danger: How Data Infrastructure Faults Cause
            Silent Failure in Agentic AI Systems
          </em>
          , Shamsiddin Khamidov, IT Park University, 2026.
        </p>
        <p>
          The benchmark, the record-level fault injector, and the{" "}
          <span className="mono">airs probe</span> scorer are in the same
          repository. Rebuild this page&rsquo;s data with{" "}
          <span className="mono">npm run data</span>.
        </p>
      </footer>
    </main>
  );
}
