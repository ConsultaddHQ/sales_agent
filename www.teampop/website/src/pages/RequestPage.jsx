import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Check, Loader2 } from 'lucide-react'
import { submitRequest } from '../lib/api'
import Navbar from '../components/Navbar'

function RequestForm({ onSuccess }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [url, setUrl] = useState('')
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState('')

  function validate() {
    const e = {}
    if (!name.trim()) e.name = 'Name is required'
    if (!email.trim()) e.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = 'Invalid email'
    if (!url.trim()) e.url = 'Store URL is required'
    else if (!url.includes('.')) e.url = 'Enter a valid URL'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    setErrors(errs)
    if (Object.keys(errs).length) return

    setLoading(true)
    setApiError('')
    try {
      const finalUrl = url.startsWith('http') ? url : `https://${url}`
      await submitRequest(name.trim(), email.trim().toLowerCase(), finalUrl)
      onSuccess({ name: name.trim(), email: email.trim().toLowerCase(), url: finalUrl })
    } catch (err) {
      setApiError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-colors no-underline mb-2"
      >
        <ArrowLeft size={12} /> Back
      </Link>

      <header className="mb-2">
        <h1 className="text-2xl font-semibold tracking-tight text-white mb-3">Get your free demo</h1>
        <p className="text-[#888888] text-sm leading-relaxed">
          Enter your details and we'll build a voice AI agent for your store.
        </p>
      </header>

      <div className="space-y-2">
        <label className="block text-[10px] uppercase tracking-[0.05em] font-medium text-zinc-400">Full Name</label>
        <input
          className="input-field"
          type="text"
          placeholder="Jane Smith"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        {errors.name && <p className="text-xs text-red-400 mt-1">{errors.name}</p>}
      </div>

      <div className="space-y-2">
        <label className="block text-[10px] uppercase tracking-[0.05em] font-medium text-zinc-400">Email Address</label>
        <input
          className="input-field"
          type="email"
          placeholder="jane@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {errors.email && <p className="text-xs text-red-400 mt-1">{errors.email}</p>}
      </div>

      <div className="space-y-2">
        <label className="block text-[10px] uppercase tracking-[0.05em] font-medium text-zinc-400">Store URL</label>
        <input
          className="input-field"
          type="text"
          placeholder="your-store.myshopify.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        {errors.url && <p className="text-xs text-red-400 mt-1">{errors.url}</p>}
      </div>

      {apiError && (
        <p className="text-sm text-red-400 bg-red-500/10 px-4 py-2 rounded-lg">{apiError}</p>
      )}

      <button
        type="submit"
        className="w-full bg-white text-black font-bold py-4 rounded-[8px] flex items-center justify-center gap-2 hover:bg-zinc-200 transition-all active:scale-[0.98] cursor-pointer border-none text-sm"
        disabled={loading}
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : null}
        {loading ? 'Submitting...' : 'Get My Demo'}
        {!loading && <span className="text-xs">&rarr;</span>}
      </button>
    </form>
  )
}

function Confirmation({ data }) {
  const calendlyUrl = import.meta.env.VITE_CALENDLY_URL

  return (
    <div className="flex flex-col items-center text-center gap-6">
      {/* Glowing checkmark */}
      <div className="relative mb-4">
        <div className="absolute inset-0 bg-white opacity-10 blur-2xl rounded-full" />
        <div className="relative w-24 h-24 rounded-full border border-[#333333] flex items-center justify-center bg-[#0e0e0e]">
          <Check size={40} className="text-white" strokeWidth={1.5} />
        </div>
      </div>

      <h1 className="text-4xl md:text-5xl font-extrabold tracking-[-0.04em] text-white">
        We're on it, {data.name}.
      </h1>

      <p className="text-lg text-[#888888] leading-relaxed max-w-xl">
        Your custom demo will be ready within 1-2 hours.
        We'll email you at <span className="text-white">{data.email}</span>.
      </p>

      {/* Gradient divider */}
      <div className="gradient-divider my-4" />

      <div className="w-full text-left">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <h2 className="text-base font-semibold uppercase tracking-wider text-white">
              Book a call while you wait
            </h2>
            <p className="text-[10px] text-zinc-500 mt-1 uppercase tracking-widest">
              Free 20-min call — we'll walk you through what we're building.
            </p>
          </div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-zinc-400 font-medium">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
            Available Slots Today
          </div>
        </div>

        {calendlyUrl && calendlyUrl !== 'https://calendly.com' ? (
          <iframe
            src={calendlyUrl}
            title="Book a call"
            className="w-full rounded-lg border border-[#222222] bg-[#111111]"
            style={{ minHeight: '600px' }}
          />
        ) : (
          <div className="w-full h-[300px] bg-[#111111] rounded-lg border border-[#222222] flex flex-col items-center justify-center gap-4">
            <div className="text-zinc-500 text-sm uppercase tracking-[0.2em]">
              Scheduler Loading...
            </div>
            <div className="grid grid-cols-4 gap-4 opacity-20">
              <div className="h-10 w-20 bg-zinc-800 rounded" />
              <div className="h-10 w-20 bg-zinc-800 rounded" />
              <div className="h-10 w-20 bg-zinc-800 rounded" />
              <div className="h-10 w-20 bg-zinc-800 rounded" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function RequestPage() {
  const [submitted, setSubmitted] = useState(null)

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <Navbar />
      <div className={`pt-24 pb-16 px-6 flex justify-center ${submitted ? 'max-w-4xl mx-auto' : ''}`}>
        {submitted ? (
          <Confirmation data={submitted} />
        ) : (
          <div className="card w-full max-w-md p-8 relative overflow-hidden">
            {/* Gradient accent line */}
            <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
            <RequestForm onSuccess={setSubmitted} />
          </div>
        )}
      </div>
    </div>
  )
}
