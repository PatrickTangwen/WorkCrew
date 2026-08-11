import "@testing-library/jest-dom/vitest"
import { vi } from "vitest"

Element.prototype.scrollIntoView = vi.fn()

// jsdom ships no canvas, so the thinking orb finds no 2d context and holds
// still. Returning null keeps it on that path without jsdom's "not
// implemented" noise.
HTMLCanvasElement.prototype.getContext = vi.fn(() => null)

window.matchMedia ??= vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
}))

window.IntersectionObserver ??= class {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
  takeRecords = vi.fn(() => [])
  root = null
  rootMargin = ""
  thresholds = []
} as unknown as typeof IntersectionObserver
