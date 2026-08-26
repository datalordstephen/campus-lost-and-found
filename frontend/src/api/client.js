// Axios instance that attaches the JWT and centralises error handling.
import axios from "axios";

const TOKEN_KEY = "clf_token";
const USER_KEY = "clf_user";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  getUser: () => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) ?? "null");
    } catch {
      return null;
    }
  },
  setUser: (user) => localStorage.setItem(USER_KEY, JSON.stringify(user)),
};

// Vite proxies these paths to the backend in dev; VITE_API_URL overrides for a
// deployed build.
const client = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "" });

client.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    // The 30-minute JWT expired (or was tampered with) — bounce to login.
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
      tokenStore.clear();
      if (window.location.pathname !== "/login") window.location.assign("/login");
    }
    return Promise.reject(error);
  },
);

/** Pull a readable message out of a FastAPI error response. */
export function errorMessage(error, fallback = "Something went wrong") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  // 422 from Pydantic: [{loc, msg, type}, ...]
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
    return field ? `${field}: ${first.msg}` : first.msg;
  }
  return error?.message ?? fallback;
}

export const api = {
  register: (body) => client.post("/auth/register", body).then((r) => r.data),
  login: (body) => client.post("/auth/login", body).then((r) => r.data),
  me: () => client.get("/auth/me").then((r) => r.data),

  submitFound: (formData) =>
    client.post("/items/found", formData).then((r) => r.data),
  reportLost: (formData) => client.post("/items/lost", formData).then((r) => r.data),
  listFound: (params) => client.get("/items/found", { params }).then((r) => r.data),
  listLost: (params) => client.get("/items/lost", { params }).then((r) => r.data),
  confirmCustody: (id) =>
    client.post(`/items/found/${id}/confirm-custody`).then((r) => r.data),

  matchesForLost: (id, k = 5) =>
    client.get(`/matches/${id}`, { params: { k } }).then((r) => r.data),
  matchesForFound: (id, k = 5) =>
    client.get(`/matches/found/${id}`, { params: { k } }).then((r) => r.data),

  createClaim: (body) => client.post("/claims/", body).then((r) => r.data),
  listClaims: (params) => client.get("/claims/", { params }).then((r) => r.data),
  myClaims: () => client.get("/claims/mine").then((r) => r.data),
  releaseClaim: (id) => client.post(`/claims/${id}/release`).then((r) => r.data),
  verifyClaim: (id) => client.post(`/claims/${id}/verify`).then((r) => r.data),

  adminUsers: (params) => client.get("/admin/users", { params }).then((r) => r.data),
  adminStats: () => client.get("/admin/stats").then((r) => r.data),
  adminSetRole: (id, role) =>
    client.patch(`/admin/users/${id}/role`, null, { params: { role } }).then((r) => r.data),
  adminDeleteFound: (id) => client.delete(`/admin/items/found/${id}`).then((r) => r.data),
  adminDeleteLost: (id) => client.delete(`/admin/items/lost/${id}`).then((r) => r.data),
  adminRebuildIndex: () => client.post("/admin/index/rebuild").then((r) => r.data),
};

/** Backend stores an OS path; the API serves the file from /uploads/<name>. */
export const imageUrl = (path) =>
  path ? `${import.meta.env.VITE_API_URL ?? ""}/uploads/${path.split("/").pop()}` : null;

export default client;
