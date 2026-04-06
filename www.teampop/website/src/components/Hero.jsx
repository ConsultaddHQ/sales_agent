import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import VoiceOrb from './VoiceOrb'

export default function Hero() {
  const containerRef = useRef(null)

  useGSAP(() => {
    // Ensure elements are visible first, then animate
    gsap.set(['.hero-line', '.hero-sub', '.hero-cta', '.hero-trust', '.hero-orb'], { opacity: 1, y: 0 })

    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })

    tl.from('.hero-line', {
      y: 60,
      opacity: 0,
      stagger: 0.12,
      duration: 0.8,
    })
    .from('.hero-sub', {
      y: 30,
      opacity: 0,
      duration: 0.7,
    }, '-=0.3')
    .from('.hero-cta', {
      y: 20,
      opacity: 0,
      duration: 0.6,
    }, '-=0.2')
    .from('.hero-trust', {
      opacity: 0,
      duration: 0.5,
    }, '-=0.1')
    .from('.hero-orb', {
      scale: 0.8,
      opacity: 0,
      duration: 1.2,
      ease: 'power2.out',
    }, 0.2)
  }, { scope: containerRef })

  return (
    <section ref={containerRef} className="relative min-h-screen flex items-center px-6 md:px-12 pt-14">
      <div className="max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        {/* Left: Text */}
        <div className="flex flex-col items-start gap-8">
          <h1 className="text-6xl md:text-8xl font-black tracking-[-0.04em] leading-[0.9] text-white">
            <span className="hero-line block">Your Store.</span>
            <span className="hero-line block">Talking back.</span>
          </h1>

          <p className="hero-sub text-xl text-[#888888] leading-relaxed max-w-md">
            Deploy hyper-intelligent conversational agents trained on your product catalog. High-fidelity voice responses delivered in under 2 hours.
          </p>

          <div className="hero-cta">
            <Link
              to="/request"
              className="bg-white text-black px-8 py-4 rounded font-bold text-lg hover:bg-neutral-200 transition-all inline-flex items-center gap-2 no-underline"
            >
              Get Your Demo <ArrowRight size={18} />
            </Link>
          </div>

          <p className="hero-trust text-sm text-[#555555]">
            No setup required &middot; No credit card &middot; We handle everything
          </p>
        </div>

        {/* Right: Voice Orb */}
        <div className="hero-orb flex justify-center lg:justify-end">
          <div className="w-[340px] h-[340px] sm:w-[440px] sm:h-[440px]">
            <VoiceOrb />
          </div>
        </div>
      </div>
    </section>
  )
}
