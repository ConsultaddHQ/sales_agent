import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import './index.css'
import App from './App.jsx'

gsap.registerPlugin(ScrollTrigger)

// Ensure GSAP ticker runs in all environments (including headless browsers)
gsap.ticker.lagSmoothing(0)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
