/* REST client for the HEALTH INFO Django API.
 * Mirrors mobile/lib/api.dart: JWT storage, X-Tenant-ID header,
 * one transparent access-token refresh on 401, envelope-aware errors. */
'use strict';

const Api = (() => {
  // Served from a dev host → talk to the local Django backend, ignoring any
  // stale prod base saved in localStorage. Prod build keeps the deployed API.
  const DEV = ['localhost', '127.0.0.1'].includes(location.hostname);
  const DEFAULT_BASE = DEV
    ? `http://${location.hostname}:8000`
    : 'https://healthinfo.pythonanywhere.com';

  let base = DEV ? DEFAULT_BASE : (localStorage.getItem('api_base') || DEFAULT_BASE);
  let tenant = localStorage.getItem('tenant_slug') || 'demo';
  // The organization's display name, kept beside the slug so the chrome can
  // name it without another call. Empty until a sign-in or a switch names it.
  let tenantName = localStorage.getItem('tenant_name') || '';
  let access = localStorage.getItem('access');
  let refresh = localStorage.getItem('refresh');
  let me = null; // cached /api/users/me/ for the session

  // Mirrors backend WRITE_ROLES / REPORT_ROLES.
  const WRITE_ROLES = new Set(['super_admin', 'tenant_admin', 'doctor', 'pharmacist']);
  const REPORT_ROLES = new Set([...WRITE_ROLES, 'nurse', 'midwife', 'chew']);

  // Nigerian mobile numbers, or the last-6-digit pharmacy short login;
  // anything else is taken to be a licence number.
  const PHONE_RE = /^(?:(?:\+234|0)[789]\d{9}|\d{6})$/;

  class ApiError extends Error {
    constructor(message, status, errors) {
      super(message);
      this.status = status;
      this.errors = errors || null; // DRF field-error dict from the envelope
    }
  }

  function headers(json, auth = true, withTenant = true) {
    // Sign-in is the one call sent with no tenant: the stored slug may belong
    // to whoever used this browser last, and the server resolves the user's
    // own organization (or the host's) instead.
    const h = withTenant ? { 'X-Tenant-ID': tenant } : {};
    if (json) h['Content-Type'] = 'application/json';
    if (auth && access) h['Authorization'] = 'Bearer ' + access;
    return h;
  }

  function url(path, query) {
    const u = new URL(base + path);
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined && v !== null && v !== '') u.searchParams.set(k, v);
      }
    }
    return u.toString();
  }

  async function refreshAccess() {
    if (!refresh) return false;
    try {
      const r = await fetch(url('/api/auth/token/refresh/'), {
        method: 'POST',
        headers: headers(true, false),
        body: JSON.stringify({ refresh }),
      });
      if (!r.ok) return false;
      access = (await r.json()).access;
      localStorage.setItem('access', access);
      return true;
    } catch {
      return false;
    }
  }

  async function fail(res) {
    let message = `Request failed (${res.status})`;
    let errors = null;
    try {
      const data = await res.json();
      // config/responses.py envelope: {success, message, errors} — or raw DRF {detail}.
      if (data && typeof data.message === 'string') message = data.message;
      else if (data && typeof data.detail === 'string') message = data.detail;
      if (data && data.errors && typeof data.errors === 'object') errors = data.errors;
    } catch { /* non-JSON body */ }
    throw new ApiError(message, res.status, errors);
  }

  /* Core request. Retries once after token refresh on 401.
   * opts: {body, query, auth:false, raw:true} */
  async function request(method, path, opts = {}) {
    const init = () => ({
      method,
      headers: headers(opts.body !== undefined, opts.auth !== false, !opts.noTenant),
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    let res = await fetch(url(path, opts.query), init());
    if (res.status === 401 && opts.auth !== false && await refreshAccess()) {
      res = await fetch(url(path, opts.query), init());
    }
    if (!res.ok) await fail(res);
    if (opts.raw) return res;
    const text = await res.text();
    return text ? JSON.parse(text) : null;
  }

  return {
    ApiError,
    get base() { return base; },
    set base(v) { base = v.replace(/\/+$/, '') || DEFAULT_BASE; localStorage.setItem('api_base', base); },
    get tenant() { return tenant; },
    set tenant(v) { tenant = v.trim(); localStorage.setItem('tenant_slug', tenant); },
    get tenantName() { return tenantName; },
    set tenantName(v) { tenantName = (v || '').trim(); localStorage.setItem('tenant_name', tenantName); },
    get isLoggedIn() { return !!access; },

    get: (path, query) => request('GET', path, { query }),
    post: (path, body) => request('POST', path, { body: body ?? {} }),
    patch: (path, body) => request('PATCH', path, { body }),
    del: (path) => request('DELETE', path, {}),
    options: (path) => request('OPTIONS', path, {}),
    public: (path, query) => request('GET', path, { query, auth: false }),

    /* DRF list endpoints paginate; return {rows, count, next, previous} either way. */
    async list(path, query) {
      const data = await request('GET', path, { query });
      if (data && typeof data === 'object' && Array.isArray(data.results)) {
        return { rows: data.results, count: data.count, next: data.next, previous: data.previous };
      }
      return { rows: data, count: Array.isArray(data) ? data.length : null, next: null, previous: null };
    },

    /* Authenticated GET returning the raw body — for endpoints that answer
       HTML rather than JSON (the printable receipt). */
    async text(path, query) {
      const res = await request('GET', path, { query, raw: true });
      return res.text();
    },

    /* Authenticated file download (CSV exports need the JWT header, so no plain <a href>). */
    async download(path, query, filename) {
      const res = await request('GET', path, { query, raw: true });
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    },

    /* `identifier` is a phone number (pharmacy staff: its last 6 digits), or
       a licence number for the clinical cadres (doctor, nurse, midwife, CHEW)
       who sign in with theirs instead. */
    async login(identifier, password) {
      const field = PHONE_RE.test(identifier.replace(/\s/g, '')) ? 'phone' : 'license_number';
      const data = await request('POST', '/api/auth/token/', {
        body: { [field]: identifier, password }, auth: false, noTenant: true,
      });
      access = data.access;
      refresh = data.refresh;
      localStorage.setItem('access', access);
      localStorage.setItem('refresh', refresh);
      me = null;
      // The token names the user's organization; every later call carries it.
      // Super-admins come back with none and keep whatever slug was set.
      if (data.tenant) {
        tenant = data.tenant;
        localStorage.setItem('tenant_slug', tenant);
        tenantName = data.tenant_name || '';
        localStorage.setItem('tenant_name', tenantName);
      }
      return data.role;
    },

    async logout() {
      // Best-effort server-side blacklist; never block the local clear.
      if (refresh) {
        try {
          await request('POST', '/api/auth/logout/', { body: { refresh }, auth: false });
        } catch { /* idempotent */ }
      }
      access = refresh = me = null;
      localStorage.removeItem('access');
      localStorage.removeItem('refresh');
    },

    /* Current user, fetched once then cached for the session. */
    async myself() {
      if (!me) me = await request('GET', '/api/users/me/');
      return me;
    },

    roleCanWrite: (role) => WRITE_ROLES.has(role),
    roleCanReport: (role) => REPORT_ROLES.has(role),
  };
})();
