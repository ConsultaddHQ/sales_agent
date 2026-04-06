import { useState, useEffect, useCallback } from 'react'
import {
  Loader2, LogOut, ExternalLink, Send, RefreshCw,
  Play, Eye, X, ChevronDown, ChevronUp,
} from 'lucide-react'
import { adminLogin, getRequests, processRequest, sendAgent } from '../lib/api'
import { timeAgo, STATUS_COLORS } from '../lib/utils'
import Navbar from '../components/Navbar'

// ── Login Gate ───────────────────────────────────────────────────────────────

function LoginGate({ onAuth }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLogin(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await adminLogin(password)
      sessionStorage.setItem('admin_password', password)
      onAuth(password)
    } catch {
      setError('Incorrect password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <form onSubmit={handleLogin} className="card w-full max-w-sm p-8 flex flex-col gap-5">
        <h1 className="text-xl font-semibold text-center">Admin</h1>
        <input
          className="input-field"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        {error && <p className="text-xs text-red-400 text-center">{error}</p>}
        <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : null}
          Sign In
        </button>
      </form>
    </div>
  )
}

// ── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${STATUS_COLORS[status] || STATUS_COLORS.pending}`}
    >
      {status === 'processing' && <Loader2 size={10} className="animate-spin" />}
      {status}
    </span>
  )
}

// ── Process Dialog ───────────────────────────────────────────────────────────

function ProcessDialog({ row, password, onClose, onProcessed }) {
  const [scrapeUrl, setScrapeUrl] = useState(row.url)
  const [storeType, setStoreType] = useState('auto')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleProcess() {
    setLoading(true)
    setError('')
    try {
      await processRequest(row.id, password, scrapeUrl, storeType)
      onProcessed(row.id)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <div className="card w-full max-w-lg p-6 flex flex-col gap-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold">Process Request</h2>
          <button onClick={onClose} className="text-[#666666] hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="text-sm text-[#888888]">
          <span className="text-[#666666]">Client URL:</span>{' '}
          <span className="text-[#ededed]">{row.url}</span>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#888888] mb-1.5">Scrape URL</label>
          <input
            className="input-field"
            type="text"
            value={scrapeUrl}
            onChange={(e) => setScrapeUrl(e.target.value)}
            placeholder="URL to actually scrape"
          />
          <p className="text-xs text-[#555555] mt-1">
            Change this if you want to scrape a different page/category than what the client submitted.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#888888] mb-1.5">Store Type</label>
          <select
            className="input-field"
            value={storeType}
            onChange={(e) => setStoreType(e.target.value)}
          >
            <option value="auto">Auto-detect</option>
            <option value="shopify">Shopify</option>
            <option value="threadless">Threadless</option>
            <option value="supermicro">Supermicro</option>
          </select>
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">{error}</p>}

        <div className="flex gap-3 justify-end mt-2">
          <button onClick={onClose} className="btn-ghost text-sm">Cancel</button>
          <button onClick={handleProcess} className="btn-primary text-sm" disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Start Processing
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Send Dialog ──────────────────────────────────────────────────────────────

function SendDialog({ row, password, baseUrl, onClose, onSent }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const testUrl = baseUrl ? `${baseUrl.replace(/\/$/, '')}${row.test_url}` : ''

  async function handleSend() {
    if (!baseUrl) return
    setLoading(true)
    setError('')
    try {
      await sendAgent(row.id, password, baseUrl)
      onSent(row.id)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <div className="card w-full max-w-md p-6 flex flex-col gap-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold">Send to {row.name}?</h2>
          <button onClick={onClose} className="text-[#666666] hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="text-sm space-y-2">
          <p><span className="text-[#666666]">Email:</span> <span className="text-[#ededed]">{row.email}</span></p>
          {testUrl ? (
            <p>
              <span className="text-[#666666]">Test URL:</span>{' '}
              <a href={testUrl} target="_blank" rel="noopener noreferrer" className="text-white hover:underline">
                {testUrl}
              </a>
            </p>
          ) : (
            <p className="text-red-400 text-xs">Set the Base URL in the top bar first.</p>
          )}
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">{error}</p>}

        <div className="flex gap-3 justify-end mt-2">
          <button onClick={onClose} className="btn-ghost text-sm">Cancel</button>
          <button onClick={handleSend} className="btn-primary text-sm" disabled={loading || !baseUrl}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send Email
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ password, onLogout }) {
  const [requests, setRequests] = useState([])
  const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem('admin_base_url') || '')
  const [processRow, setProcessRow] = useState(null)
  const [sendRow, setSendRow] = useState(null)
  const [expandedError, setExpandedError] = useState(null)

  const fetchRequests = useCallback(async () => {
    try {
      const data = await getRequests(password)
      setRequests(data)
    } catch {
      // silently fail on poll
    }
  }, [password])

  useEffect(() => {
    fetchRequests()
    const id = setInterval(fetchRequests, 30000)
    return () => clearInterval(id)
  }, [fetchRequests])

  function handleBaseUrlChange(e) {
    const val = e.target.value
    setBaseUrl(val)
    localStorage.setItem('admin_base_url', val)
  }

  function optimisticUpdate(id, status) {
    setRequests((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status } : r))
    )
  }

  return (
    <div className="min-h-screen pt-20 pb-12 px-6">
      {/* Top bar */}
      <div className="max-w-6xl mx-auto mb-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Hyperflex Admin</h1>
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <label className="text-[10px] text-[#555555] font-medium mb-0.5">Base URL</label>
            <input
              className="input-field text-xs !py-1.5 !px-3 w-64"
              placeholder="https://abc.ngrok-free.dev"
              value={baseUrl}
              onChange={handleBaseUrlChange}
            />
          </div>
          <button onClick={onLogout} className="btn-ghost text-xs mt-3.5">
            <LogOut size={12} /> Out
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="max-w-6xl mx-auto card overflow-hidden">
        {requests.length === 0 ? (
          <div className="p-16 text-center text-sm text-[#555555]">
            No requests yet. Share your landing page to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#222222] text-[#666666] text-xs uppercase tracking-wider">
                  <th className="text-left p-4 font-medium">Name</th>
                  <th className="text-left p-4 font-medium">Email</th>
                  <th className="text-left p-4 font-medium">URL</th>
                  <th className="text-left p-4 font-medium">Status</th>
                  <th className="text-left p-4 font-medium">Created</th>
                  <th className="text-right p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((row) => (
                  <tr key={row.id} className="border-b border-[#1a1a1a] hover:bg-white/[0.02] transition-colors">
                    <td className="p-4 font-medium">{row.name}</td>
                    <td className="p-4 text-[#888888]">{row.email}</td>
                    <td className="p-4">
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-white hover:underline inline-flex items-center gap-1"
                        title={row.url}
                      >
                        {row.url.replace(/^https?:\/\//, '').slice(0, 30)}
                        <ExternalLink size={10} />
                      </a>
                    </td>
                    <td className="p-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="p-4 text-[#666666] text-xs">{timeAgo(row.created_at)}</td>
                    <td className="p-4 text-right">
                      <div className="flex items-center gap-2 justify-end">
                        {row.status === 'pending' && (
                          <button
                            onClick={() => setProcessRow(row)}
                            className="btn-primary !py-1.5 !px-3 text-xs"
                          >
                            Process
                          </button>
                        )}

                        {row.status === 'processing' && (
                          <span className="text-xs text-[#666666] flex items-center gap-1">
                            <Loader2 size={12} className="animate-spin" /> Processing...
                          </span>
                        )}

                        {row.status === 'ready' && (
                          <>
                            {baseUrl && row.test_url && (
                              <a
                                href={`${baseUrl.replace(/\/$/, '')}${row.test_url}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn-ghost !py-1.5 !px-3 text-xs"
                              >
                                <Eye size={12} /> Preview
                              </a>
                            )}
                            <button
                              onClick={() => setSendRow(row)}
                              className="btn-primary !py-1.5 !px-3 text-xs"
                            >
                              <Send size={12} /> Send
                            </button>
                          </>
                        )}

                        {row.status === 'sent' && (
                          <>
                            {baseUrl && row.test_url && (
                              <a
                                href={row.test_url.startsWith('http') ? row.test_url : `${baseUrl.replace(/\/$/, '')}${row.test_url}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn-ghost !py-1.5 !px-3 text-xs"
                              >
                                <Eye size={12} /> View
                              </a>
                            )}
                            <button
                              onClick={() => setSendRow(row)}
                              className="text-xs text-[#666666] hover:text-[#888888] transition-colors flex items-center gap-1"
                            >
                              <RefreshCw size={10} /> Resend
                            </button>
                          </>
                        )}

                        {row.status === 'failed' && (
                          <>
                            <button
                              onClick={() => setProcessRow(row)}
                              className="btn-primary !py-1.5 !px-3 text-xs"
                            >
                              Retry
                            </button>
                            <button
                              onClick={() => setExpandedError(expandedError === row.id ? null : row.id)}
                              className="text-[#666666] hover:text-white transition-colors"
                            >
                              {expandedError === row.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </button>
                          </>
                        )}
                      </div>

                      {row.status === 'failed' && expandedError === row.id && row.error_message && (
                        <div className="mt-2 text-xs text-red-400 bg-red-500/10 p-2 rounded-lg text-left">
                          {row.error_message}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Dialogs */}
      {processRow && (
        <ProcessDialog
          row={processRow}
          password={password}
          onClose={() => setProcessRow(null)}
          onProcessed={(id) => optimisticUpdate(id, 'processing')}
        />
      )}
      {sendRow && (
        <SendDialog
          row={sendRow}
          password={password}
          baseUrl={baseUrl}
          onClose={() => setSendRow(null)}
          onSent={(id) => optimisticUpdate(id, 'sent')}
        />
      )}
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const [password, setPassword] = useState(() => sessionStorage.getItem('admin_password') || '')
  const authed = !!password

  function handleLogout() {
    sessionStorage.removeItem('admin_password')
    setPassword('')
  }

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <Navbar />
      {authed ? (
        <Dashboard password={password} onLogout={handleLogout} />
      ) : (
        <LoginGate onAuth={setPassword} />
      )}
    </div>
  )
}
