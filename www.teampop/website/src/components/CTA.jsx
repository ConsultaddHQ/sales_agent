import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

export default function CTA() {
  const sectionRef = useRef(null)
  const contentRef = useRef(null)

  useGSAP(() => {
    gsap.set(contentRef.current, { opacity: 1, y: 0 })

    gsap.from(contentRef.current, {
      y: 30,
      opacity: 0,
      duration: 0.8,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: sectionRef.current,
        start: 'top 85%',
        toggleActions: 'play none none none',
      },
    })
  }, { scope: sectionRef })

  return (
    <section ref={sectionRef} className="py-32 px-6 md:px-12 border-t border-[#1a1a1a]">
      <div ref={contentRef} className="max-w-7xl mx-auto flex flex-col items-center text-center gap-10">
        <h2 className="text-5xl md:text-7xl font-black tracking-[-0.04em] text-white max-w-3xl leading-[1.1]">
          Ready to hear your store talk?
        </h2>
        <Link
          to="/request"
          className="bg-white text-black px-10 py-4 rounded font-bold text-lg hover:bg-neutral-200 transition-all inline-flex items-center gap-2 no-underline"
        >
          Start Building Now <ArrowRight size={18} />
        </Link>
      </div>
    </section>
  )
}
