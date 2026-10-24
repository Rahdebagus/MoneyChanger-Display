// ─── Currency Configuration ───────────────────────────────────────────────────

export const API_BASE = "https://claudecaludy-pam-rate-backend.hf.space";

export const CURRENCY_LABELS = {
  USD: "US Dollar",
  USDT: "US Dollar Tether",
  USDK: "US Dollar Thousand",
  AUD: "Australian Dollar",
  EUR: "Euro",
  GBP: "British Pound",
  CHF: "Swiss Franc",
  JPY: "Japanese Yen",
  SGD: "Singapore Dollar",
  CAD: "Canadian Dollar",
  MYR: "Malaysian Ringgit",
  NZD: "New Zealand Dollar",
  HKD: "Hong Kong Dollar",
  CNY: "Chinese Yuan",
  BND: "Brunei Dollar",
  SAR: "Saudi Riyal",
  AED: "UAE Dirham",
  THB: "Thai Baht",
  PHP: "Philippine Peso",
  KRW: "Korean Won",
  INR: "Indian Rupee",
  NTD: "New Taiwan Dollar",
};

export const ALL_CURRENCIES = Object.keys(CURRENCY_LABELS);

export const LEFT_COL = ["USD", "AUD", "EUR", "GBP", "CHF", "JPY", "SGD", "CAD", "MYR"];

export const RIGHT_COL = [
  "NZD", "HKD", "CNY", "BND", "SAR", "AED",
  "THB", "PHP", "KRW", "INR", "NTD"
];

export const STEPS = [
  { n: 1, label: "Upload Image" },
  { n: 2, label: "Edit Rates" },
  { n: 3, label: "Download" },
];

export const SUPPORTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export const APP_VERSION = "v1.0";
export const APP_NAME = "PAM Money Changer";
export const APP_COMPANY = "PT. PRADNYANA ARTHA MANDIRI";
