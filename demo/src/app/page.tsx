import type { Metadata } from "next";
import Conversation from "@/components/Conversation";

export const metadata: Metadata = {
  title: "Ask your pipeline — AIRS",
  description:
    "Ask a question of your data pipeline and find out whether the answer was right — " +
    "and if not, whether the pipeline or the model was at fault. Runs on your machine.",
};

export default function Page() {
  return (
    <main>
      <Conversation />
    </main>
  );
}
