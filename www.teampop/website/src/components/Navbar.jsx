import { Link } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#000000] border-b border-[#1a1a1a]">
      <div className="max-w-7xl mx-auto px-6 md:px-12 h-14 flex items-center justify-between">
        <Link to="/" className="text-xl font-black tracking-[-0.04em] text-white no-underline">
          Hyperflex
        </Link>

        <Link to="/request" className="btn-primary px-4 py-1.5 rounded-lg text-sm">
          Get Started
        </Link>
      </div>
    </nav>
  )
}
