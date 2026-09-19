import type { Metadata } from "next";
import CheckPipeline from "@/components/CheckPipeline";

export const metadata: Metadata = {
  title: "Check my pipeline — AIRS",
  description:
    "Score how ready your data pipeline is for an AI agent, from a sample of its records. " +
    "Runs on your machine; no model call, no API key.",
};

export default function Page() {
  return (
    <main>
      <CheckPipeline />
    </main>
  );
}
