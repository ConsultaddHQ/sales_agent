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

// Public
export function submitRequest(name, email, url) {
  return request('/api/submit-request', {
    method: 'POST',
    body: JSON.stringify({ name, email, url }),
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
