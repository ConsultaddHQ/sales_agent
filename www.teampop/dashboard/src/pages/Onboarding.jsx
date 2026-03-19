import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, CircleAlert, Loader2, Sparkles, Eye, Copy, Check } from 'lucide-react';

const FLOW_STATUS = {
  IDLE: 'idle',
  PROCESSING: 'processing',
  SUCCESS: 'success',
  ERROR: 'error',
};

const PROGRESS_MESSAGES = [
  'Validating Shopify store...',
  'Scraping product catalog...',
  'Downloading product images...',
  'Creating vector embeddings...',
  'Creating AI agent...',
  'Generating test page...',
];

const normalizeStoreUrl = (value) => {
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
};

// Error messages mapping
const ERROR_MESSAGES = {
  invalid_url: {
    title: 'Invalid URL',
    message: 'Please enter a valid URL (e.g., example.myshopify.com or https://example.com)',
  },
  not_shopify_store: {
    title: 'Not a Shopify Store',
    message: "This doesn't appear to be a Shopify store. Please enter a valid Shopify store URL.",
  },
  password_protected: {
    title: 'Store is Password Protected',
    message: 'This store is password-protected. Please disable the password in your Shopify settings and try again.',
    help: 'Go to Shopify Admin → Online Store → Preferences → Password Protection',
  },
  no_products_found: {
    title: 'No Products Found',
    message: 'No products found in this store. Please add and publish products first.',
  },
  rate_limited: {
    title: 'Rate Limited',
    message: 'Shopify is rate-limiting requests. Please try again in 2-3 minutes.',
  },
  agent_creation_error: {
    title: 'Agent Creation Failed',
    message: 'Failed to create AI agent. Please try again or contact support.',
  },
};

export default function Onboarding() {
  const navigate = useNavigate();
  const [storeUrl, setStoreUrl] = useState('');
  const [status, setStatus] = useState(FLOW_STATUS.IDLE);
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [inputError, setInputError] = useState('');
  const [onboardingData, setOnboardingData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (status !== FLOW_STATUS.PROCESSING) return undefined;

    const intervalId = setInterval(() => {
      setCurrentMessageIndex((prev) => (prev + 1) % PROGRESS_MESSAGES.length);
    }, 5000);

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
    setErrorCode('');
    setCurrentMessageIndex(0);
    setStatus(FLOW_STATUS.PROCESSING);

    try {
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8005';
      const response = await fetch(`${backendUrl}/onboard`, {
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
        // Handle structured error response
        const errorData = payload.detail || payload;
        const code = errorData.error_code || 'unknown_error';
        const message = errorData.error_message || 'Failed to onboard store. Please try again.';
        
        setErrorCode(code);
        setErrorMessage(message);
        setStatus(FLOW_STATUS.ERROR);
        return;
      }

      if (!payload.success) {
        throw new Error('Onboarding completed but returned success=false');
      }

      if (!payload.store_id || !payload.agent_id) {
        throw new Error('Missing store_id or agent_id in response');
      }

      setOnboardingData(payload);
      setStatus(FLOW_STATUS.SUCCESS);
    } catch (error) {
      setErrorCode('unknown_error');
      setErrorMessage(error.message || 'Unexpected error while onboarding.');
      setStatus(FLOW_STATUS.ERROR);
    }
  };

  const resetToIdle = () => {
    setStatus(FLOW_STATUS.IDLE);
    setErrorMessage('');
    setErrorCode('');
    setOnboardingData(null);
  };

  const handleCopySnippet = () => {
    if (onboardingData?.widget_snippet) {
      navigator.clipboard.writeText(onboardingData.widget_snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handlePreviewWidget = () => {
    if (onboardingData?.test_url) {
      // Open test page in new window
      const testUrl = `http://localhost:8080${onboardingData.test_url}`;
      window.open(testUrl, '_blank', 'width=1200,height=800');
    }
  };

  const renderContent = () => {
    // PROCESSING STATE
    if (status === FLOW_STATUS.PROCESSING) {
      return (
        <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full border border-brand-400/30 bg-brand-500/10 shadow-[0_0_50px_rgba(99,102,241,0.25)]">
            <Loader2 className="h-9 w-9 animate-spin text-brand-300" />
          </div>
          <h2 className="text-center text-2xl font-semibold text-white">Training Your AI Agent</h2>
          <p className="mt-3 text-center text-sm text-zinc-400">
            This can take 30-60 seconds while we process your store.
          </p>

          <div className="mt-8 rounded-xl border border-white/10 bg-zinc-950/90 p-4 font-mono text-sm text-zinc-300">
            <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
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

    // SUCCESS STATE
    if (status === FLOW_STATUS.SUCCESS && onboardingData) {
      return (
        <div className="w-full max-w-3xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-500/10">
            <CheckCircle2 className="h-10 w-10 text-emerald-400" />
          </div>
          
          <h2 className="text-center text-3xl font-semibold text-white">Your AI Sales Agent is Ready!</h2>
          <p className="mt-3 text-center text-zinc-400">
            {onboardingData.products_count} products indexed • Agent trained and deployed
          </p>

          {/* Action Buttons */}
          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={handlePreviewWidget}
              className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-brand-400"
            >
              <Eye className="h-4 w-4" />
              Preview Widget
            </button>
            
            <button
              onClick={handleCopySnippet}
              className="flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-6 py-3 text-sm font-medium text-white transition hover:bg-white/10"
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="h-4 w-4" />
                  Copy Widget Code
                </>
              )}
            </button>
          </div>

          {/* Widget Snippet */}
          <div className="mt-8">
            <h3 className="text-sm font-medium text-zinc-300 mb-2">Installation Code</h3>
            <div className="rounded-xl border border-white/10 bg-zinc-950/90 p-4 font-mono text-xs text-zinc-300 overflow-x-auto">
              <pre className="whitespace-pre-wrap">{onboardingData.widget_snippet}</pre>
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              Paste this code before the closing &lt;/body&gt; tag in your Shopify theme
            </p>
          </div>

          {/* Store Details */}
          <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <div className="text-zinc-500 text-xs">Store ID</div>
              <div className="text-white font-mono text-xs mt-1">{onboardingData.store_id.slice(0, 8)}...</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <div className="text-zinc-500 text-xs">Agent ID</div>
              <div className="text-white font-mono text-xs mt-1">{onboardingData.agent_id.slice(0, 12)}...</div>
            </div>
          </div>

          <div className="mt-8 text-center">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="text-sm text-zinc-400 hover:text-white transition"
            >
              Back to Home
            </button>
          </div>
        </div>
      );
    }

    // ERROR STATE
    if (status === FLOW_STATUS.ERROR) {
      const errorInfo = ERROR_MESSAGES[errorCode] || {
        title: 'Error',
        message: errorMessage || 'An unexpected error occurred',
      };

      return (
        <div className="w-full max-w-xl rounded-2xl border border-red-400/30 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border border-red-400/30 bg-red-500/10">
            <CircleAlert className="h-8 w-8 text-red-400" />
          </div>
          
          <h2 className="text-center text-2xl font-semibold text-white">{errorInfo.title}</h2>
          <p className="mt-3 text-center text-sm text-red-300">{errorInfo.message}</p>
          
          {errorInfo.help && (
            <div className="mt-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3">
              <p className="text-xs text-yellow-200">
                <strong>Tip:</strong> {errorInfo.help}
              </p>
            </div>
          )}

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

    // IDLE STATE (Input Form)
    return (
      <div className="w-full max-w-xl rounded-2xl border border-white/10 bg-zinc-900/70 p-8 shadow-2xl backdrop-blur">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full border border-brand-400/30 bg-brand-500/10">
          <Sparkles className="h-8 w-8 text-brand-300" />
        </div>
        
        <h1 className="text-center text-3xl font-semibold tracking-tight text-white">
          Onboard Your Shopify Store
        </h1>
        <p className="mt-3 text-center text-sm text-zinc-400">
          Enter your store URL and we'll train your AI sales agent automatically
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
              placeholder="example.myshopify.com or https://example.com"
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-4 py-3 text-white placeholder:text-zinc-500 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
            {inputError && (
              <p className="mt-2 text-sm text-red-400">{inputError}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={!storeUrl.trim()}
            className="w-full rounded-xl bg-brand-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-400 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            Start Training
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <div className="mt-6 rounded-lg border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-zinc-400">
            <strong className="text-zinc-300">What happens next:</strong>
            <br />
            We'll scrape your products, create embeddings, and deploy a voice AI agent trained on your catalog.
            This typically takes 30-60 seconds.
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-4">
      {renderContent()}
    </div>
  );
}
