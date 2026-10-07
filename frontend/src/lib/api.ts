export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/** Policy fields the user answers in the UI (sent with every request; the server stores nothing). */
export type CurrencyAnswers = {
  currency_map: Record<string, string>;
  conversion_basis: "transaction_date" | "latest" | null;
};

export type Policy = Partial<CurrencyAnswers> & Record<string, any>;

export class ApiError extends Error {
  status: number;
  detail: any;

  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.error || "The API request failed.");
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** 409: the question's scope has currencies the user has not confirmed yet. */
  get isCurrencyConfirmation() {
    return this.status === 409 && this.detail?.error === "CURRENCY_CONFIRMATION_REQUIRED";
  }

  /** 422: a hand-built / invalid plan (unknown entity, bad column ...). */
  get isInvalidPlan() {
    return this.status === 422 && this.detail?.error === "INVALID_PLAN";
  }

  /** Plain readable text for any error body (string detail, pydantic list, or object). */
  get readable(): string {
    const d = this.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join("; ");
    if (d?.problems?.length) return d.problems.join("; ");
    return d?.message || d?.error || this.message;
  }
}

async function request(path: string, init: RequestInit = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, init);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body);
  return body;
}

function jsonRequest(body: any): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export async function uploadDataset(file: File, overwrite = false) {
  const formData = new FormData();
  formData.append("file", file);
  return request(`/datasets/upload${overwrite ? "?overwrite=true" : ""}`, {
    method: "POST",
    body: formData,
  });
}

export async function getProfile(filename: string = "sales.csv") {
  return request("/profile", jsonRequest({ filename }));
}

export async function createPlan(question: string, filename: string = "sales.csv", policy: Policy = {}) {
  return request("/plan", jsonRequest({ question, filename, policy }));
}

const planCall = (path: string) => (plan: any, filename: string = "sales.csv", policy: Policy = {}) =>
  request(path, jsonRequest({ plan, filename, policy }));

export const checkCurrency = planCall("/currency/check");
export const executePlan = planCall("/execute");
export const verifyPlan = planCall("/verify");
export const getTrust = planCall("/trust");
export const getProof = planCall("/proof");
export const getImpact = planCall("/impact");
export const getSensitivity = planCall("/sensitivity");

export async function generateReport(proofBundle: any, reportType: string = "verified") {
  return request("/reports/generate", jsonRequest({ proof_bundle: proofBundle, report_type: reportType }));
}
