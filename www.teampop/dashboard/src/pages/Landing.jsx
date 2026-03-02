import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Sparkles, Zap } from 'lucide-react';

export default function Landing() {
  const [url, setUrl] = useState('');
  const navigate = useNavigate();

  const handleStart = (e) => {
    e.preventDefault();
    if (!url) return;
    
    // Quick validation to ensure it has a protocol
    let finalUrl = url;
    if (!/^https?:\/\//i.test(finalUrl)) {
      finalUrl = 'https://' + finalUrl;
    }
    
    // Navigate to onboarding, passing the URL to state
    navigate('/onboarding', { state: { url: finalUrl } });
  };

  return (
    <div className="min-h-screen flex flex-col items-center pt-32 pb-16 px-6 relative overflow-hidden bg-[#020617]">
      {/* Dynamic Background Effects */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-brand-600/20 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute top-[20%] right-[-10%] w-[30%] h-[50%] bg-purple-600/10 blur-[120px] rounded-full pointer-events-none" />

      {/* Header */}
      <header className="absolute top-0 left-0 right-0 p-6 flex justify-between items-center z-10 w-full max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-purple-500 flex items-center justify-center shadow-lg">
            <Bot size={24} className="text-white" />
          </div>
          <span className="font-bold text-xl tracking-tight text-white">Team Pop</span>
        </div>
        <button className="text-sm font-medium text-slate-300 hover:text-white transition-colors">
          Sign In
        </button>
      </header>

      {/* Hero Content */}
      <main className="flex-1 flex flex-col items-center justify-center max-w-4xl w-full z-10 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-sm font-medium text-brand-300 mb-8 backdrop-blur-md">
          <Sparkles size={16} />
          <span>Next-Gen AI Agents Powered by WebRTC</span>
        </div>
        
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 leading-[1.1] text-white">
          The Zero-Friction Voice AI <br className="hidden md:block" />
          <span className="text-gradient">for your E-commerce Store.</span>
        </h1>
        
        <p className="text-lg md:text-xl text-slate-400 max-w-2xl mb-12">
          Deploy an intelligent, voice-native AI agent that knows your entire catalog. Enter your website, let our crawler learn your inventory, and drop the widget into your store in 60 seconds.
        </p>

        {/* Input Form */}
        <form 
          onSubmit={handleStart}
          className="w-full max-w-xl flex flex-col sm:flex-row gap-4 relative group"
        >
          <div className="relative flex-1">
            <div className="absolute -inset-1 bg-gradient-to-r from-brand-500 to-purple-500 rounded-2xl blur opacity-25 group-focus-within:opacity-50 transition duration-500" />
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Enter your website URL (e.g., store.com)"
              className="relative w-full px-6 py-4 bg-[#0B1120] border border-slate-800 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500 shadow-xl text-lg"
              required
            />
          </div>
          
          <button 
            type="submit"
            className="flex items-center justify-center gap-2 px-8 py-4 bg-white text-slate-900 font-semibold rounded-2xl hover:bg-slate-100 transition-all shadow-xl hover:shadow-2xl hover:-translate-y-0.5"
          >
            <span>Start Magic Crawl</span>
            <Zap size={20} className="text-brand-600" />
          </button>
        </form>
        
        <div className="mt-8 flex items-center gap-6 text-sm text-slate-500">
          <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-green-500" /> No credit card required</div>
          <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-blue-500" /> Magic instant training</div>
        </div>
      </main>
    </div>
  );
}
