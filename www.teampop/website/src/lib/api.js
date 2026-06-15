const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8005'

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

function adminHeaders(password) {
  return { 'X-Admin-Password': password }
}

// Public. `extra` carries assisted-close context (conversation_id, source)
// so the backend can attach the sales transcript/PIC to the lead.
export function submitRequest(name, email, url, extra = {}) {
  return request('/api/submit-request', {
    method: 'POST',
    body: JSON.stringify({ name, email, url, ...extra }),
  })
}

// Admin
export function adminLogin(password) {
  return request('/api/admin/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}

export function getRequests(password) {
  return request('/api/requests', { headers: adminHeaders(password) })
}

export function processRequest(id, password, scrapeUrl, storeType = 'auto') {
  return request(`/api/process-request/${id}`, {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify({ scrape_url: scrapeUrl, store_type: storeType }),
  })
}

export function updateRequest(id, password, data) {
  return request(`/api/update-request/${id}`, {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify(data),
  })
}

export function sendAgent(id, password, baseUrl) {
  return request(`/api/send-agent/${id}`, {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify({ base_url: baseUrl }),
  })
}

export function switchModel(password, agentId, storeId, llmModel) {
  return request('/api/switch-model', {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify({ agent_id: agentId, store_id: storeId, llm_model: llmModel }),
  })
}

// Sales Proof Library (Phase 3)
export function listProof(password) {
  return request('/api/proof', { headers: adminHeaders(password) })
}

export function createProof(password, data) {
  return request('/api/proof', {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify(data),
  })
}

export function updateProof(password, id, data) {
  return request(`/api/proof/${id}`, {
    method: 'POST',
    headers: adminHeaders(password),
    body: JSON.stringify(data),
  })
}

export function deleteProof(password, id) {
  return request(`/api/proof/${id}/delete`, {
    method: 'POST',
    headers: adminHeaders(password),
  })
}
