import React, { useState, useEffect, useMemo } from 'react';
import AvatarWidget from '../components/AvatarWidget';
import { api } from '../services/api';
import '../styles/GetStarted.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function GetStarted() {
    // --- Data States ---
    const [url, setUrl] = useState('');
    const [crawlStatus, setCrawlStatus] = useState('idle'); // 'idle' | 'running' | 'completed' | 'failed'
    const [docCount, setDocCount] = useState(0);
    const [crawlError, setCrawlError] = useState('');

    // --- UI States ---
    const [activeStep, setActiveStep] = useState(0);
    const [completedSteps, setCompletedSteps] = useState({ 0: false, 1: false, 2: false });

    // --- Computed Values ---
    const normalizedDomain = useMemo(() => {
        try {
            const parsed = new URL(url);
            return parsed.hostname.replace(/^www\./, '');
        } catch {
            return url.replace(/^https?:\/\//, '').replace(/^www\./, '');
        }
    }, [url]);

    const widgetScript = useMemo(() => {
        const scriptSrc = 'http://localhost:5173/widget.js';
        return `<script src="${scriptSrc}" data-domain="${normalizedDomain}" data-api="${API_BASE_URL}"></script>`;
    }, [normalizedDomain]);

    const isUrlValid = useMemo(() => {
        try {
            const parsed = new URL(url);
            return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && parsed.hostname.includes('.');
        } catch {
            return false;
        }
    }, [url]);

    // --- Actions ---

    // Step 0 -> Step 1
    const handleStartCrawl = async () => {
        setCrawlError('');
        setCrawlStatus('running');
        setCompletedSteps(prev => ({ ...prev, 0: true }));
        setActiveStep(1);

        try {
            await api.startCrawl(url);
        } catch (err) {
            setCrawlStatus('failed');
            setCrawlError('Failed to initiate crawl. : ',err)
        }
    };

    // Step 1 Polling
    useEffect(() => {
        if (activeStep !== 1 || crawlStatus === 'idle') return;

        let pollInterval;
        const poll = async () => {
            try {
                // Check Status
                const statusData = await api.getCrawlStatus(url);
                if (statusData.status) {
                    setCrawlStatus(statusData.status);
                    if (statusData.status === 'failed') {
                        setCrawlError(statusData.error || 'Crawl failed');
                    }
                }

                // Check Count
                const countData = await api.getCrawlCount(url);
                if (typeof countData.count === 'number') {
                    setDocCount(countData.count);
                }

                // Auto-advance if completed
                if (statusData.status === 'completed') {
                    setCompletedSteps(prev => ({ ...prev, 1: true })); 
                }

            } catch (e) {
                console.error("Polling error", e);
            }
        };

        // Poll immediately then interval
        poll();
        pollInterval = setInterval(poll, 3000);

        return () => clearInterval(pollInterval);
    }, [activeStep, crawlStatus, url]);


    // Step 1 -> Step 2
    const handleGoToPreview = () => {
        setCompletedSteps(prev => ({ ...prev, 1: true }));
        setActiveStep(2);
    };

    // Start Over
    const handleStartOver = () => {
        // Reset Data
        setUrl('');
        setDocCount(0);
        setCrawlStatus('idle');
        setCrawlError('');

        // Reset UI
        setActiveStep(0);
        setCompletedSteps({ 0: false, 1: false, 2: false });
        
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // --- Render Helpers ---

    return (
        <div className="page-content">
            <div className="timeline-container">
                
                {/* Header */}
                <div style={{ marginBottom: '40px', textAlign: 'center' }}>
                    <h1>Train your AI</h1>
                    <p style={{ color: 'var(--text-1)' }}>Setup your assistant in 3 simple steps.</p>
                </div>

                {/* --- Step 0: Input --- */}
                <div className={`timeline-item ${activeStep === 0 ? 'active' : ''} ${completedSteps[0] ? 'completed' : ''}`}>
                    <div className="timeline-marker">
                        {completedSteps[0] ? '✓' : '1'}
                    </div>
                    <div className="timeline-content">
                        <h3>Add your website</h3>
                        {activeStep === 0 && (
                            <div className="step-body">
                                <p style={{marginBottom: '16px', fontSize: '14px', color: 'var(--text-1)'}}>
                                    Paste the URL you want your assistant to learn from.
                                </p>
                                <div className="input-group">
                                    <input 
                                        type="text" 
                                        placeholder="https://example.com"
                                        value={url}
                                        onChange={(e) => setUrl(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && isUrlValid && handleStartCrawl()}
                                        autoFocus
                                    />
                                    <button 
                                        className="btn" 
                                        disabled={!isUrlValid} 
                                        onClick={handleStartCrawl}
                                    >
                                        Continue
                                    </button>
                                </div>
                                <div style={{height:'10px'}}>
                                  {!isUrlValid && url.length > 5 && <span className="error-text">Please enter a valid HTTP/HTTPS URL</span>}
                                </div>
                            </div>
                        )}
                        {completedSteps[0] && activeStep !== 0 && (
                             <div style={{ padding: '8px 0', fontSize:'14px', color:'var(--text-1)'}}>
                                 Target: <strong style={{color:'var(--text-0)'}}>{url}</strong>
                             </div>
                        )}
                    </div>
                </div>

                {/* --- Step 1: Crawl --- */}
                <div className={`timeline-item ${activeStep === 1 ? 'active' : ''} ${completedSteps[1] ? 'completed' : ''}`}>
                    <div className="timeline-marker">
                        {completedSteps[1] ? '✓' : '2'}
                    </div>
                    <div className="timeline-content">
                        <div className="card-title-group">
                            <h3>Crawl & Index</h3>
                            {activeStep === 1 && <span className={`status-chip ${crawlStatus}`}>{crawlStatus}</span>}
                        </div>
                        
                        {activeStep === 1 && (
                            <div className="step-body">
                                <div className="crawler-status">
                                    <div className="crawl-stat-item">
                                        <div className="stat-label">Pages Found</div>
                                        <div className="stat-value">{docCount}</div>
                                    </div>
                                    <div className="crawl-stat-item">
                                        <div className="stat-label">Domain</div>
                                        <div className="stat-value">{normalizedDomain}</div>
                                    </div>
                                </div>

                                {crawlError && (
                                    <div className="error-text" style={{marginBottom: '16px'}}>
                                        Error: {crawlError}
                                    </div>
                                )}

                                <div className="action-row">
                                    <button 
                                        className="btn btn-secondary" 
                                        onClick={() => api.startCrawl(url)} // Quick retry
                                        disabled={crawlStatus === 'running'}
                                    >
                                        {crawlStatus === 'running' ? 'Crawling...' : 'Restart Crawl'}
                                    </button>
                                    
                                    <button 
                                        className="btn"
                                        onClick={handleGoToPreview}
                                        disabled={crawlStatus !== 'completed'}
                                    >
                                        Next: Preview
                                    </button>
                                </div>
                            </div>
                        )}
                         {completedSteps[1] && activeStep !== 1 && (
                             <div style={{ padding: '8px 0', fontSize:'14px', color:'var(--text-1)'}}>
                                 Indexed <strong>{docCount}</strong> pages.
                             </div>
                        )}
                    </div>
                </div>

                {/* --- Step 2: Preview --- */}
                <div className={`timeline-item ${activeStep === 2 ? 'active' : ''} ${completedSteps[2] ? 'completed' : ''}`}>
                    <div className="timeline-marker">
                       {completedSteps[2] ? '✓' : '3'}
                    </div>
                    <div className="timeline-content">
                        <h3>Preview & Install</h3>
                        {activeStep === 2 && (
                            <div className="step-body">
                                <div className="preview-install-grid">
                                    {/* Left: Preview */}
                                    <div className="preview-pane">
                                        <AvatarWidget domain={url} preview />
                                    </div>

                                    {/* Right: Install */}
                                    <div className="install-pane">
                                        <h4 style={{margin:0}}>Embed Code</h4>
                                        <p style={{fontSize: '13px', color: 'var(--text-1)', lineHeight: 1.4}}>
                                            Add this to your <code>&lt;head&gt;</code> tag to go live.
                                        </p>
                                        <div className="script-box">
                                            {widgetScript}
                                        </div>
                                        <button 
                                            className="btn btn-secondary" 
                                            onClick={() => navigator.clipboard.writeText(widgetScript)}
                                            style={{fontSize:'13px'}}
                                        >
                                            Copy Code
                                        </button>
                                    </div>
                                </div>

                                <div style={{ marginTop: '30px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '20px' }}>
                                    <button className="btn btn-secondary" onClick={handleStartOver}>
                                        Start Over With New URL
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
}
