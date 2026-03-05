import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, CircleAlert, Loader2, Sparkles } from 'lucide-react';
import InstallSnippet from '../components/InstallSnippet';

const FLOW_STATUS = {
  IDLE: 'idle',
  PROCESSING: 'processing',
  SUCCESS: 'success',
  ERROR: 'error',
};

const PROGRESS_MESSAGES = [
  'Connecting to Shopify Store...',
  'Scraping product catalog...',
  'Chunking text data...',
  'Generating Vector Embeddings via OpenAI...',
  'Deploying AI Agent...',
];

const normalizeStoreUrl = (value) => {
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
};

export default function Onboarding() {
  const navigate = useNavigate();
  const [storeUrl, setStoreUrl] = useState('');
  const [status, setStatus] = useState(FLOW_STATUS.IDLE);
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [inputError, setInputError] = useState('');
  const [storeId, setStoreId] = useState('');

  useEffect(() => {
    if (status !== FLOW_STATUS.PROCESSING) return undefined;

    const intervalId = setInterval(() => {
      setCurrentMessageIndex((prev) => (prev + 1) % PROGRESS_MESSAGES.length);
    }, 4000);

    return () => clearInterval(intervalId);
  }, [status]);

  const processingMessage = useMemo(
    () => PROGRESS_MESSAGES[currentMessageIndex],
    [currentMessageIndex]
  );

  const handleOnboard = async (event) => {
    event.preventDefault();
    const normalizedUrl = normalizeStoreUrl(storeUrl);
    if (!normalizedUrl) {
      setInputError('Shopify Store URL is required.');
      return;
    }

    setInputError('');
    setErrorMessage('');
    setCurrentMessageIndex(0);
    setStatus(FLOW_STATUS.PROCESSING);

    try {
      const response = await fetch('http://localhost:8000/onboard', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: normalizedUrl }),
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }

      if (!response.ok) {
        const detail =
          typeof payload?.detail === 'string' && payload.detail.trim()
            ? payload.detail.trim()
            : 'Failed to train the AI agent. Please verify the URL and try again.';
        throw new Error(detail);
      }

      if (!payload.store_id) {
        throw new Error('Onboarding completed, but no store_id was returned by the backend.');
      }

      setStoreId(payload.store_id);
      setStatus(FLOW_STATUS.SUCCESS);
    } catch (error) {
      setErrorMessage(error.message || 'Unexpected error while onboarding.');
      setStatus(FLOW_STATUS.ERROR);
    }
  };

  const resetToIdle = () => {
    setStatus(FLOW_STATUS.IDLE);
    setErrorMessage('');
  };

  const renderContent = () => {
    if (status === FLOW_STATUS.PROCESSING) {
      return (
        <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full border border-brand-400/30 bg-brand-500/10 shadow-[0_0_50px_rgba(99,102,241,0.25)]">
            <Loader2 className="h-9 w-9 animate-spin text-brand-300" />
          </div>
          <h2 className="text-center text-2xl font-semibold text-white">Training Your AI Agent</h2>
          <p className="mt-3 text-center text-sm text-zinc-400">
            This can take 30-60 seconds while we scrape and embed your catalog.
          </p>

          <div className="mt-8 rounded-xl border border-white/10 bg-zinc-950/90 p-4 font-mono text-sm text-zinc-300">
            <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              Live Training Log
            </div>
            <div className="flex items-center gap-3">
              <Loader2 className="h-4 w-4 animate-spin text-brand-300" />
              <span>{processingMessage}</span>
            </div>
          </div>
        </div>
      );
    }

    if (status === FLOW_STATUS.SUCCESS) {
      return (
        <div className="w-full max-w-3xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-500/10">
            <CheckCircle2 className="h-10 w-10 text-emerald-400" />
          </div>
          <h2 className="text-center text-3xl font-semibold text-white">Your AI Sales Agent is Ready!</h2>
          <p className="mt-3 text-center text-zinc-400">
            Copy and paste this snippet into your storefront to install the widget.
          </p>

          <div className="mt-8">
            <InstallSnippet tenantId={storeId} />
          </div>

          <div className="mt-8 text-center">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="rounded-xl border border-white/15 bg-white/5 px-6 py-3 text-sm font-medium text-white transition hover:bg-white/10"
            >
              Finish
            </button>
          </div>
        </div>
      );
    }

    if (status === FLOW_STATUS.ERROR) {
      return (
        <div className="w-full max-w-xl rounded-2xl border border-red-400/30 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border border-red-400/30 bg-red-500/10">
            <CircleAlert className="h-8 w-8 text-red-400" />
          </div>
          <h2 className="text-center text-2xl font-semibold text-white">Training Failed</h2>
          <p className="mt-3 text-center text-sm text-red-300">{errorMessage}</p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <button
              type="button"
              onClick={resetToIdle}
              className="rounded-xl bg-red-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-red-400"
            >
              Try Again
            </button>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/10"
            >
              Back to Home
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
        <h1 className="text-center text-3xl font-semibold tracking-tight text-white">Onboard Your Shopify Store</h1>
        <p className="mt-3 text-center text-sm text-zinc-400">
          Enter your store URL and we will train your AI sales agent automatically.
        </p>

        <form onSubmit={handleOnboard} className="mt-8 space-y-4">
          <div>
            <label htmlFor="shopify-url" className="mb-2 block text-sm font-medium text-zinc-300">
              Shopify Store URL
            </label>
            <input
              id="shopify-url"
              type="text"
              value={storeUrl}
              onChange={(event) => {
                setStoreUrl(event.target.value);
                if (inputError) setInputError('');
              }}
              placeholder="mystore.myshopify.com"
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white placeholder:text-zinc-500 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
            {inputError ? <p className="mt-2 text-sm text-red-300">{inputError}</p> : null}
          </div>

          <button
            type="submit"
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-zinc-900 transition hover:bg-zinc-200"
          >
            Train AI Agent
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>
      </div>
    );
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-zinc-950 px-6 py-20 text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.20),transparent_48%)]" />
      <div className="pointer-events-none absolute -left-24 top-1/3 h-72 w-72 rounded-full bg-cyan-500/10 blur-[100px]" />
      <div className="pointer-events-none absolute -right-24 top-24 h-72 w-72 rounded-full bg-brand-500/15 blur-[110px]" />

      <header className="mx-auto mb-10 flex w-full max-w-5xl items-center">
        <button type="button" onClick={() => navigate('/')} className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
            <Sparkles className="h-4 w-4 text-white" />
          </span>
          <span className="text-sm font-semibold tracking-wide text-zinc-200">Team Pop Dashboard</span>
        </button>
      </header>

      <main className="mx-auto flex w-full max-w-5xl items-center justify-center">{renderContent()}</main>
    </div>
  );
}
