// ─── useAuth ──────────────────────────────────────────────────────────────────
//
// Lives apart from the provider so the context file exports only a component.

import { useContext } from "react";

import { AuthContext } from "../context/authContext.js";

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
