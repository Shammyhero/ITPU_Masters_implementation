import type { Metadata } from "next";
import Link from "next/link";
import data from "@/data/aist.json";
import AskTheAgent from "@/components/AskTheAgent";
import Challenge, { type Case } from "@/components/Challenge";
import Inversion, { type InversionData } from "@/components/Inversion";
import Legibility, { type LegibilityData } from "@/components/Legibility";
import Stress, { type StressData } from "@/components/Stress";

export const metadata: Metadata = {
  title: "Why trust the score — AIRS",
  description:
    "Why agents fail silently on degraded data, and what a pipeline score can tell you " +
    "before you deploy one. Every figure exported from the benchmark runs.",
};

export default function Evidence() {
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

      <section>
        <span className="act">Act 4</span>
        <h2>So measure the pipeline instead</h2>
        <p className="sub">
          If the consumer cannot tell you when it is failing, score what you feed it.
          The probe reads a sample of your own records — on your machine, with no model
          call — and says which dimension is degraded and how much of the score rests on
          what it could actually measure.
        </p>
        <Link className="cta link-cta" href="/">Check my pipeline →</Link>
      </section>

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
