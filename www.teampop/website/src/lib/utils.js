import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export function timeAgo(dateString) {
  const now = new Date()
  const date = new Date(dateString)
  const seconds = Math.floor((now - date) / 1000)

  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString()
}

export const STATUS_COLORS = {
  pending: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  ready: 'bg-green-500/10 text-green-400 border-green-500/20',
  sent: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
}
