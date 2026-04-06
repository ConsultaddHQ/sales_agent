import { useRef, useEffect, useState, useCallback } from 'react'
import { Globe, Cpu, Sparkles } from 'lucide-react'

const cards = [
  {
    icon: Globe,
    step: '01',
    tag: 'Instant',
    dotColor: '#22c55e',
    title: 'Tell us your store',
    desc: 'Connect your Shopify, custom storefront, or any product catalog. We ingest your entire inventory in seconds.',
  },
  {
    icon: Cpu,
    step: '02',
    tag: 'Custom AI',
    dotColor: '#3b82f6',
    title: 'We build your agent',
    desc: "Our system generates a custom-tuned voice AI agent for your brand's voice and inventory. No coding required. Ready in under 2 hours.",
  },
  {
    icon: Sparkles,
    step: '03',
    tag: 'Live Preview',
    dotColor: '#a855f7',
    title: 'Test it live',
    desc: 'Preview the agent on a private test link. Try it yourself before any commitment.',
  },
]

function StepCard({ card, index, progress }) {
  const [hovered, setHovered] = useState(false)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const cardRef = useRef(null)

  const handleMouseMove = useCallback((e) => {
    if (!cardRef.current) return
    const rect = cardRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left - rect.width / 2) / rect.width
    const y = (e.clientY - rect.top - rect.height / 2) / rect.height
    setMousePos({ x, y })
  }, [])

  // Stagger: each card starts animating at a different scroll point
  const staggerOffset = index * 0.15
  const cardProgress = Math.max(0, Math.min(1, (progress - staggerOffset) / (1 - staggerOffset * 2)))

  // Winterfell-style: cards come from bottom with slight rotation, scale up
  const rotations = [-4, 0, 4]
  const startRotate = rotations[index]
  const rotate = startRotate * (1 - cardProgress)
  const translateY = 120 * (1 - cardProgress)
  const scale = 0.88 + 0.12 * cardProgress
  const opacity = cardProgress

  // Hover tilt
  const tiltX = hovered ? -mousePos.y * 8 : 0
  const tiltY = hovered ? mousePos.x * 8 : 0

  return (
    <div
      ref={cardRef}
      className="group relative rounded-xl border border-[#222] bg-[#111] p-7 flex flex-col gap-5 cursor-default will-change-transform"
      style={{
        transform: `perspective(800px) translateY(${translateY}px) scale(${scale}) rotate(${rotate}deg) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`,
        opacity,
        transition: hovered
          ? 'border-color 0.3s, box-shadow 0.3s'
          : 'border-color 0.3s, box-shadow 0.3s',
        borderColor: hovered ? '#333' : '#222',
        boxShadow: hovered ? '0 0 30px rgba(255,255,255,0.04)' : 'none',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => { setHovered(false); setMousePos({ x: 0, y: 0 }) }}
    >
      {/* Icon */}
      <div className="w-12 h-12 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg flex items-center justify-center group-hover:border-[#333] transition-colors">
        <card.icon size={20} className="text-white" />
      </div>

      {/* Step label + accent dot */}
      <div className="flex items-center gap-2">
        <span className="text-[#555] font-mono text-xs uppercase tracking-wider">Step {card.step}</span>
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: card.dotColor }} />
      </div>

      {/* Title */}
      <h3 className="text-xl font-semibold text-white">{card.title}</h3>

      {/* Description */}
      <p className="text-sm text-[#777] leading-relaxed">{card.desc}</p>

      {/* Tag pill — pushed to bottom */}
      <div className="mt-auto pt-2">
        <span className="inline-block text-[10px] font-medium uppercase tracking-widest text-[#888] bg-[#1a1a1a] border border-[#2a2a2a] px-3 py-1.5 rounded-full group-hover:border-[#444] group-hover:text-white transition-all">
          {card.tag}
        </span>
      </div>
    </div>
  )
}

export default function HowItWorks() {
  const sectionRef = useRef(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = sectionRef.current
    if (!el) return

    const handleScroll = () => {
      const rect = el.getBoundingClientRect()
      const windowH = window.innerHeight
      // Start animation when top of section enters bottom of viewport
      // Complete when section is ~40% visible
      const start = windowH
      const end = windowH * 0.3
      const raw = 1 - (rect.top - end) / (start - end)
      setProgress(Math.max(0, Math.min(1, raw)))
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll() // initial check
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Fallback: ensure visible after 2.5s even if scroll listener doesn't fire
  useEffect(() => {
    const timer = setTimeout(() => setProgress(p => Math.max(p, 1)), 2500)
    return () => clearTimeout(timer)
  }, [])

  return (
    <section ref={sectionRef} className="py-32 px-6 md:px-12">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div
          className="flex flex-col gap-4 mb-16"
          style={{
            opacity: Math.min(1, progress * 2),
            transform: `translateY(${30 * (1 - Math.min(1, progress * 2))}px)`,
          }}
        >
          <span className="text-[10px] font-medium tracking-[0.05em] uppercase text-[#555]">
            How it works
          </span>
          <h2 className="text-4xl md:text-5xl font-medium tracking-tight text-white">
            Three steps. That&apos;s it.
          </h2>
        </div>

        {/* 3 equal cards in a row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {cards.map((card, i) => (
            <StepCard key={card.step} card={card} index={i} progress={progress} />
          ))}
        </div>
      </div>
    </section>
  )
}
