"use client";

import { useState } from "react";

/** Act 3: the natural next thought — "just check the confidence" — measured. */
export default function AskTheAgent() {
  const [step, setStep] = useState(0);
  return (
    <section>
      <span className="act">Act 3</span>
      <h2>So ask the agent how sure it is</h2>
      <p className="sub">
        The obvious defence: let the agent flag its own shaky answers. Every
        decision in this study logged a confidence score, so that idea is
        testable rather than arguable.
      </p>

      <div className="panel">
        {step === 0 && (
          <div className="guess">
            <p>
              Across {`~11,400`} decisions, how well did the agent&rsquo;s own
              confidence predict whether it was about to fail silently?
            </p>
            <p className="src">
              Measured as AUC. 1.00 is perfect; <b>0.50 is a coin flip.</b>
            </p>
            <div className="tabs">
              {["Near perfect (0.9)", "Useful (0.7)", "Weak (0.6)", "Useless (0.5)"].map(
                (label, i) => (
                  <button key={i} className="tab" onClick={() => setStep(1)}>
                    {label}
                  </button>
                ),
              )}
            </div>
          </div>
        )}
        {step === 1 && (
          <div className="reveal bad">
            <div className="big-num">0.501</div>
            <div className="reveal-t">A coin flip. Exactly.</div>
            <p>
              On the retrieval task the agent&rsquo;s confidence carries{" "}
              <b>no information at all</b> about whether it is wrong. It reports
              1.00 on answers that are right and 1.00 on answers that are wrong.
              You cannot ask it.
            </p>
            <p>
              The same score computed from <em>pipeline telemetry alone</em> —
              no agent involved, no model called — reaches <b>0.580</b>{" "}
              (DeLong p = 0.0001). Not a large number. But it is available before
              you deploy anything, and it beats the only alternative.
            </p>
            <p className="key">
              If the consumer cannot tell you when it is failing, measure what
              you feed it instead.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
