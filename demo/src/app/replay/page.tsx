import type { Metadata } from "next";
import Replay from "@/components/Replay";

export const metadata: Metadata = {
  title: "Recorded runs — AIRS",
  description:
    "Real decisions from the benchmark, played through the same console you would " +
    "use on your own pipeline. No server needed.",
};

export default function Page() {
  return (
    <main>
      <Replay />
    </main>
  );
}
