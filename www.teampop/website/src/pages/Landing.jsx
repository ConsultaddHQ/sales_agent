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
      <div id="top"><Hero /></div>
      <div id="how-it-works"><HowItWorks /></div>
      <div id="faq"><FAQ /></div>
      <div id="cta"><CTA /></div>
      <Footer />
    </div>
  )
}
