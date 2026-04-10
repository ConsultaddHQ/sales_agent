import { useState, useRef, useEffect } from 'react'
import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

const faqs = [
  {
    q: 'How long does setup take?',
    a: 'Under 2 hours. You give us your store URL, we crawl your catalog, train the voice agent on your products, and deliver a working demo. No coding, no integrations, no waiting.',
  },
  {
    q: 'Do I need to be on Shopify?',
    a: "No. We support Shopify, custom storefronts, Threadless artist shops, and more. If your products are on the web, we can ingest them.",
  },
  {
    q: 'What does the voice agent actually do?',
    a: 'It answers customer questions about your products using natural conversation. Think of it as a knowledgeable sales associate that knows your entire catalog, available 24/7.',
  },
  {
    q: 'Is there a free trial?',
    a: "Yes. Your first demo is completely free — no credit card required. We build a fully functional voice agent for your store so you can test it before any commitment.",
  },
  {
    q: 'Can I customize the voice?',
    a: "Absolutely. We tune the agent to match your brand's tone — whether casual and friendly or professional and concise. Voice, pacing, and personality are all configurable.",
  },
  {
    q: 'How accurate are the recommendations?',
    a: 'Very. The agent uses semantic search across your entire catalog, understanding context and intent — not just keyword matching.',
  },
]

function FAQItem({ faq, isOpen, onToggle }) {
  return (
    <div className="border-t border-[#222]">
      <button
        onClick={onToggle}
        className="w-full py-5 flex items-center justify-between text-left cursor-pointer bg-transparent border-none transition-opacity duration-200 hover:opacity-70"
      >
        <span className={`text-[15px] font-medium transition-colors duration-200 ${isOpen ? 'text-white' : 'text-[#aaa]'}`}>
          {faq.q}
        </span>
        <span
          className={`ml-6 flex-shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-45' : ''}`}
        >
          <Plus size={18} className={`transition-colors duration-200 ${isOpen ? 'text-white' : 'text-[#555]'}`} />
        </span>
      </button>

      <div
        className="grid overflow-hidden transition-all duration-300 ease-out"
        style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
      >
        <div className="min-h-0 pb-5 pr-12">
          <p className="text-sm text-[#666] leading-relaxed">{faq.a}</p>
        </div>
      </div>
    </div>
  )
}

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState(null)
  const sectionRef = useRef(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const handleScroll = () => {
      const rect = el.getBoundingClientRect()
      const windowH = window.innerHeight
      const raw = 1 - (rect.top - windowH * 0.3) / (windowH * 0.7)
      setProgress(Math.max(0, Math.min(1, raw)))
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => setProgress(p => Math.max(p, 1)), 2500)
    return () => clearTimeout(timer)
  }, [])

  const fadeIn = (delay = 0) => ({
    opacity: Math.max(0, Math.min(1, (progress - delay) * 3)),
    transform: `translateY(${Math.max(0, 30 * (1 - Math.min(1, (progress - delay) * 3)))}px)`,
  })

  return (
    <section ref={sectionRef} className="py-32 px-6 md:px-12">
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-20">

          {/* Left column — large heading + CTA */}
          <div className="flex flex-col items-start justify-between gap-16" style={fadeIn(0)}>
            {/* Big heading */}
            <h2 className="text-6xl md:text-8xl font-black tracking-[-0.04em] leading-[0.9] text-white">
              FAQs
            </h2>

            {/* Bottom CTA block */}
            <div className="flex flex-col gap-4">
              <p className="text-[#999] text-sm">
                Have another question?
              </p>
              <p className="text-[#666] text-sm leading-relaxed">
                Reach out — we&apos;re happy to help.
              </p>
              <div className="flex items-center gap-4 mt-2">
                <Link
                  to="/request"
                  className="inline-flex items-center gap-2 bg-white text-black text-sm font-medium px-5 py-2 rounded hover:bg-neutral-200 transition-colors no-underline"
                >
                  Get in touch
                </Link>
              </div>
            </div>
          </div>

          {/* Right column — accordion */}
          <div style={fadeIn(0.1)}>
            {faqs.map((faq, i) => (
              <FAQItem
                key={i}
                faq={faq}
                isOpen={openIndex === i}
                onToggle={() => setOpenIndex(openIndex === i ? null : i)}
              />
            ))}
            {/* Bottom border for last item */}
            <div className="border-t border-[#222]" />
          </div>

        </div>
      </div>
    </section>
  )
}
