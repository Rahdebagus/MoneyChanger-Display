// ─── Footer Component ─────────────────────────────────────────────────────────

import { APP_NAME, APP_COMPANY } from "../../constants/currencies.js";

export function Footer() {
  return (
    <footer
      style={{
        textAlign: "center",
        padding: "32px",
        color: "#B0BEC5",
        fontSize: 12,
      }}
    >
      {APP_NAME} · Internal Rate System · {APP_COMPANY}
    </footer>
  );
}
