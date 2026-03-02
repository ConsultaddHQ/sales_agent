import React, { useState } from 'react';
import { Check, Clipboard, Terminal } from 'lucide-react';

export default function InstallSnippet({ tenantId = '<THE_TENANT_ID>' }) {
  const [copied, setCopied] = useState(false);

  const snippet = `<script src="https://cdn.teampop.com/widget.js"></script>
<team-pop-agent client-id="${tenantId}"></team-pop-agent>`;

  const handleCopy = () => {
    navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full max-w-2xl mx-auto rounded-2xl bg-[#0f172a] border border-[#1e293b] overflow-hidden shadow-2xl relative">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1e293b]/50 border-b border-[#1e293b]">
        <div className="flex items-center gap-2 text-slate-400">
          <Terminal size={16} />
          <span className="text-sm font-medium font-mono">index.html</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-sm text-slate-300 transition-colors"
        >
          {copied ? (
            <>
              <Check size={14} className="text-green-400" />
              <span className="text-green-400">Copied</span>
            </>
          ) : (
            <>
              <Clipboard size={14} />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>

      {/* Code Area */}
      <div className="p-6 overflow-x-auto">
        <pre className="font-mono text-sm leading-relaxed">
          <code className="text-slate-300">
            <span className="text-pink-400">&lt;script</span>
            <span className="text-brand-300"> src</span>
            <span className="text-slate-400">=</span>
            <span className="text-green-300">"https://cdn.teampop.com/widget.js"</span>
            <span className="text-pink-400">&gt;&lt;/script&gt;</span>
            {'\n\n'}
            <span className="text-pink-400">&lt;team-pop-agent</span>
            <span className="text-brand-300"> client-id</span>
            <span className="text-slate-400">=</span>
            <span className="text-green-300">"{tenantId}"</span>
            <span className="text-pink-400">&gt;&lt;/team-pop-agent&gt;</span>
          </code>
        </pre>
      </div>

      {/* Polish Gradient */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-brand-500/10 blur-[50px] pointer-events-none" />
    </div>
  );
}
