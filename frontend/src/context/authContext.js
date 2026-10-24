// ─── Auth Context Object ──────────────────────────────────────────────────────
//
// The context lives in its own module so AuthContext.jsx exports only a
// component and Fast Refresh keeps working during development.

import { createContext } from "react";

export const AuthContext = createContext(null);
