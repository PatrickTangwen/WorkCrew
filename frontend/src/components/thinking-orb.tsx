import { useEffect, useRef } from "react"

import {
  drawOrb,
  orbOptions,
  ORB_LABELS,
  parseInk,
  type OrbState,
} from "@/lib/thinking-orb"

type ThinkingOrbProps = {
  state?: OrbState
  size?: number
  /** Dot colour, as a hex or `r, g, b` triple. Defaults to the theme accent. */
  ink?: string
  speed?: number
  label?: string
}

/**
 * The dotted orb that marks whichever stage the engine is working on. It runs
 * only while on screen, on a visible tab, and with motion allowed; otherwise it
 * holds a single still frame.
 */
function ThinkingOrb({
  state = "working",
  size = 16,
  ink,
  speed = 1,
  label,
}: ThinkingOrbProps) {
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const element = canvas.current
    if (element === null) return
    const context = element.getContext("2d")
    if (context === null) return

    const dpr = Math.min(2, window.devicePixelRatio || 1)
    element.width = Math.round(size * dpr)
    element.height = Math.round(size * dpr)

    const options = orbOptions(state, size)
    const colour = parseInk(
      ink ??
        getComputedStyle(document.documentElement).getPropertyValue("--brand")
    )
    const rate = options.tuning.speed * speed
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    function frame(time: number) {
      context!.setTransform(dpr, 0, 0, dpr, 0, 0)
      context!.clearRect(0, 0, size, size)
      drawOrb(context!, size, time, colour, options)
    }

    // A held frame is the resting state: reduced motion never leaves it, and a
    // hidden or scrolled-away orb returns to painting only when it comes back.
    frame(reduced ? 0.6 : (performance.now() / 1000) * rate)
    if (reduced) return

    let handle = 0
    let running = false
    let visible = true

    function loop() {
      frame((performance.now() / 1000) * rate)
      handle = requestAnimationFrame(loop)
    }

    function sync() {
      const wanted = visible && document.visibilityState !== "hidden"
      if (wanted === running) return
      running = wanted
      if (wanted) handle = requestAnimationFrame(loop)
      else cancelAnimationFrame(handle)
    }

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      sync()
    })
    observer.observe(element)
    document.addEventListener("visibilitychange", sync)
    sync()

    return () => {
      cancelAnimationFrame(handle)
      observer.disconnect()
      document.removeEventListener("visibilitychange", sync)
    }
  }, [ink, size, speed, state])

  return (
    <canvas
      ref={canvas}
      role="img"
      aria-label={label ?? ORB_LABELS[state]}
      style={{ width: size, height: size }}
      className="block shrink-0"
    />
  )
}

export { ThinkingOrb }
