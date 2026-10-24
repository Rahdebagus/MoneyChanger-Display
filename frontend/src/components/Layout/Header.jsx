// ─── Generator Step Indicator ─────────────────────────────────────────────────
//
// The app chrome (logo, navigation, account) now lives in AppLayout, so this
// is only the Upload → Edit → Download progress strip for the generator page.

import { StepBadge } from "../Steps/Common/StepBadge";
import { STEPS } from "../../constants/currencies.js";

export function Header({ currentStep }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #E3F2FD",
        borderRadius: 14,
        padding: "14px 18px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        flexWrap: "wrap",
        boxShadow: "0 2px 12px rgba(21,101,192,0.06)",
      }}
    >
      {STEPS.map((step) => (
        <StepBadge
          key={step.n}
          {...step}
          active={currentStep === step.n}
          done={currentStep > step.n}
        />
      ))}
    </div>
  );
}
