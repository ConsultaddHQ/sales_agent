import Navbar from '../components/Navbar'
import Hero from '../components/Hero'
import HowItWorks from '../components/HowItWorks'
import FAQ from '../components/FAQ'
import CTA from '../components/CTA'
import Footer from '../components/Footer'

export default function Landing() {
  return (
    <div className="min-h-screen bg-[var(--background)]">
      <Navbar />
      <Hero />
      <HowItWorks />
      <FAQ />
      <CTA />
      <Footer />
    </div>
  )
}
