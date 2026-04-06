import { useRef, useEffect, useCallback, useState } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

const PARTICLE_COUNT = 18
const canHover = typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches

function createParticles() {
  return Array.from({ length: PARTICLE_COUNT }, () => ({
    angle: Math.random() * Math.PI * 2,
    radius: 140 + Math.random() * 80,
    speed: 0.002 + Math.random() * 0.006,
    size: 0.8 + Math.random() * 0.7,
    opacity: 0.1 + Math.random() * 0.25,
  }))
}

export default function VoiceOrb() {
  const containerRef = useRef(null)
  const orbRef = useRef(null)
  const glowRef = useRef(null)
  const shimmerRef = useRef(null)
  const ring1Ref = useRef(null)
  const ring2Ref = useRef(null)
  const ring3Ref = useRef(null)
  const canvasRef = useRef(null)
  const shockwaveRef = useRef(null)
  const timelineRef = useRef(null)

  // ── GSAP idle animations ──
  useGSAP(() => {
    const tl = gsap.timeline()
    timelineRef.current = tl

    // Orb breathing
    gsap.to(orbRef.current, {
      scale: 1.05,
      duration: 3,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
    })

    // Glow pulse
    gsap.to(glowRef.current, {
      opacity: 0.15,
      scale: 1.2,
      duration: 4,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
    })

    // Shimmer rotation
    gsap.to(shimmerRef.current, {
      rotation: 360,
      duration: 10,
      repeat: -1,
      ease: 'none',
    })

    // Ring ripples — continuous outward expansion
    const rings = [ring1Ref.current, ring2Ref.current, ring3Ref.current]
    rings.forEach((ring, i) => {
      gsap.fromTo(ring,
        { scale: 1, opacity: 0.12 },
        {
          scale: 1.6,
          opacity: 0,
          duration: 3 + i * 0.5,
          repeat: -1,
          ease: 'power1.out',
          delay: i * 1,
        }
      )
    })
  }, { scope: containerRef })

  // ── Mouse interactions ──
  const handleMouseMove = useCallback((e) => {
    if (!canHover) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left - rect.width / 2
    const y = e.clientY - rect.top - rect.height / 2

    // Tilt
    const rotateX = -y / 15
    const rotateY = x / 15
    gsap.to(orbRef.current, {
      rotateX,
      rotateY,
      duration: 0.5,
      ease: 'power2.out',
    })

    // Proximity glow follow
    const dist = Math.sqrt(x * x + y * y)
    const maxDist = 300
    const intensity = Math.max(0.3, 1 - dist / maxDist)
    gsap.to(glowRef.current, {
      x: x * 0.15,
      y: y * 0.15,
      opacity: intensity * 0.2,
      duration: 0.5,
      ease: 'power2.out',
    })
  }, [])

  const handleMouseLeave = useCallback(() => {
    if (!canHover) return
    gsap.to(orbRef.current, {
      rotateX: 0,
      rotateY: 0,
      duration: 1,
      ease: 'elastic.out(1, 0.3)',
    })
    gsap.to(glowRef.current, {
      x: 0,
      y: 0,
      opacity: 0.08,
      duration: 1,
      ease: 'power2.out',
    })
  }, [])

  // Hover escalation on orb itself
  const handleOrbEnter = useCallback(() => {
    if (!canHover) return
    gsap.to(glowRef.current, { opacity: 0.3, scale: 1.3, duration: 0.4 })
    gsap.to(orbRef.current, {
      boxShadow: '0 0 120px rgba(255,255,255,0.15), inset -20px -20px 50px rgba(0,0,0,0.8), inset 20px 20px 50px rgba(255,255,255,0.15)',
      duration: 0.4,
    })
  }, [])

  const handleOrbLeave = useCallback(() => {
    if (!canHover) return
    gsap.to(glowRef.current, { opacity: 0.08, scale: 1, duration: 0.6 })
    gsap.to(orbRef.current, {
      boxShadow: '0 0 80px rgba(255,255,255,0.1), inset -20px -20px 50px rgba(0,0,0,0.8), inset 20px 20px 50px rgba(255,255,255,0.1)',
      duration: 0.6,
    })
  }, [])

  // ── Click effect: push-back + glow burst + shockwave ring ──
  const handleOrbClick = useCallback(() => {
    const orb = orbRef.current
    const glow = glowRef.current
    const shock = shockwaveRef.current
    if (!orb) return

    // 1. Push-back: squish down then spring back
    gsap.timeline()
      .to(orb, {
        scale: 0.88,
        duration: 0.1,
        ease: 'power2.in',
      })
      .to(orb, {
        scale: 1.08,
        duration: 0.5,
        ease: 'elastic.out(1.2, 0.4)',
      })
      .to(orb, {
        scale: 1,
        duration: 0.3,
        ease: 'power2.out',
      })

    // 2. Glow burst: flash bright then fade
    gsap.timeline()
      .to(glow, {
        opacity: 0.5,
        scale: 1.6,
        duration: 0.15,
        ease: 'power2.out',
      })
      .to(glow, {
        opacity: 0.08,
        scale: 1,
        duration: 0.8,
        ease: 'power2.inOut',
      })

    // 3. Orb flash: briefly brighten the box-shadow
    gsap.timeline()
      .to(orb, {
        boxShadow: '0 0 200px rgba(255,255,255,0.35), inset -20px -20px 50px rgba(0,0,0,0.6), inset 20px 20px 60px rgba(255,255,255,0.3)',
        duration: 0.15,
      })
      .to(orb, {
        boxShadow: '0 0 80px rgba(255,255,255,0.1), inset -20px -20px 50px rgba(0,0,0,0.8), inset 20px 20px 50px rgba(255,255,255,0.1)',
        duration: 0.6,
        ease: 'power2.out',
      })

    // 4. Shockwave ring: expand outward from orb
    if (shock) {
      gsap.fromTo(shock,
        { scale: 0.8, opacity: 0.4, borderWidth: 2 },
        {
          scale: 2.5,
          opacity: 0,
          borderWidth: 0.5,
          duration: 0.8,
          ease: 'power2.out',
        }
      )
    }

    // 5. Quick burst on existing rings
    const rings = [ring1Ref.current, ring2Ref.current, ring3Ref.current]
    rings.forEach((ring, i) => {
      gsap.to(ring, {
        opacity: 0.25,
        duration: 0.1,
        delay: i * 0.05,
        onComplete: () => {
          gsap.to(ring, { opacity: 0, duration: 0.4 })
        },
      })
    })
  }, [])

  // ── Particle canvas ──
  useEffect(() => {
    if (!canHover) return // Skip particles on touch devices

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const particles = createParticles()
    let animId

    function resize() {
      const rect = canvas.parentElement.getBoundingClientRect()
      canvas.width = rect.width
      canvas.height = rect.height
    }
    resize()
    window.addEventListener('resize', resize)

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const cx = canvas.width / 2
      const cy = canvas.height / 2

      for (const p of particles) {
        p.angle += p.speed
        const px = cx + Math.cos(p.angle) * p.radius
        const py = cy + Math.sin(p.angle) * p.radius

        ctx.beginPath()
        ctx.arc(px, py, p.size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255, 255, 255, ${p.opacity})`
        ctx.fill()
      }
      animId = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="orb-container flex items-center justify-center relative"
      style={{ width: '100%', height: '100%', minHeight: 400 }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Particle canvas */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 0 }}
      />

      {/* Glow */}
      <div ref={glowRef} className="orb-glow" style={{ zIndex: 10 }} />

      {/* Rings */}
      <div ref={ring1Ref} className="voice-ring" style={{ width: 320, height: 320, zIndex: 10 }} />
      <div ref={ring2Ref} className="voice-ring" style={{ width: 380, height: 380, zIndex: 10 }} />
      <div ref={ring3Ref} className="voice-ring" style={{ width: 440, height: 440, zIndex: 10 }} />

      {/* Shockwave ring (triggered on click) */}
      <div
        ref={shockwaveRef}
        className="voice-ring"
        style={{ width: 280, height: 280, zIndex: 15, opacity: 0, borderColor: 'rgba(255,255,255,0.3)' }}
      />

      {/* The Orb */}
      <div
        ref={orbRef}
        className="voice-orb cursor-pointer"
        style={{ zIndex: 20 }}
        onMouseEnter={handleOrbEnter}
        onMouseLeave={handleOrbLeave}
        onClick={handleOrbClick}
      >
        <div className="orb-reflection" />
        <div ref={shimmerRef} className="orb-shimmer" />
      </div>

      {/* Status indicator */}
      <div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 flex items-center gap-2 text-[10px] tracking-widest uppercase text-[#666666] font-mono"
        style={{ zIndex: 30 }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
        Voice Agent Active
      </div>
    </div>
  )
}
