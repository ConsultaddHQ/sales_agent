import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import RequestPage from './pages/RequestPage'
import AdminPage from './pages/AdminPage'
import SalesAgent from './components/SalesAgent'

export default function App() {
  return (
    <BrowserRouter>
      <SalesAgent />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/request" element={<RequestPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </BrowserRouter>
  )
}
