// Dotted "working" orb, ported from Jakubantalik/thinking-orbs
// (src/engine/core.ts + src/engine/orbits.ts) by way of the WorkCrew design
// project's thinking-orb.js. Plain 2D canvas arcs, z-sorted and depth-shaded.
//
// This module is the drawing engine only: it holds no timers and touches no
// DOM beyond the context it is handed. The React wrapper owns the loop.

export type OrbState = "working" | "breathing" | "solving" | "shaping"

type OrbMode = "orbits" | "ring" | "rubik" | "morph"

/** A preset's constants. Each mode reads its own subset; all read `speed`. */
type OrbTuning = Record<string, number>

/** A resolved preset: which renderer to run, and the numbers it runs on. */
export type OrbOptions = { mode: OrbMode; tuning: OrbTuning }

type Dot = { x: number; y: number; z: number; r: number; white: number; a?: number }

// Shipped presets with the count/radius multipliers pre-applied. Each state has
// a small (under 40px) and a large variant rather than one scaled geometry.
const PRESETS: Record<OrbState, { mode: OrbMode; small: OrbTuning; large: OrbTuning }> = {
  working: {
    mode: "orbits",
    small: { speed: 3.9, orbitN: 3, ghostN: 10, ghostR: 2.16, ghostA: 0.5, particles: 3, partR: 2.88, partRDepth: 3.84, rsPow: 0.6, rMin: 0.3 },
    large: { speed: 1.885, orbitN: 12, ghostN: 40, ghostR: 0.9, ghostA: 0.5, particles: 3, partR: 1.2, partRDepth: 1.6, rsPow: 0.6, rMin: 0.3 },
  },
  breathing: {
    mode: "ring",
    small: { speed: 3.78, lanes: 2, segs: 15, ghostN: 0, faceOn: 1, rBase: 1.7842, rDepth: 2.7574, spin: 0, bandMul: 3.968, wobMul: 0.565, rsPow: 0.6, rMin: 0.3 },
    large: { speed: 3.24, lanes: 2, segs: 44, ghostN: 0, faceOn: 1, rBase: 1.0516, rDepth: 1.6252, spin: 0, bandMul: 3.627, wobMul: 0.368, rsPow: 0.6, rMin: 0.3 },
  },
  solving: {
    mode: "rubik",
    small: { speed: 1.95, latRings: 4, lonDensity: 12, moveCount: 14, rBase: 1.14, rDepth: 3.23, rActive: 0.57, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
    large: { speed: 1.82, latRings: 9, lonDensity: 24, moveCount: 14, rBase: 0.63, rDepth: 1.785, rActive: 0.315, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
  },
  shaping: {
    mode: "morph",
    small: { speed: 2.08, rDot: 0.021231, iconD: 0.53, spread: 1.45, rMin: 0.25 },
    large: { speed: 2.405, rDot: 0.008295, iconD: 0.702, spread: 1.45, rMin: 0.25 },
  },
}

function fibDir(i: number, n: number) {
  const golden = Math.PI * (3 - Math.sqrt(5))
  const y = 1 - (2 * (i + 0.5)) / n
  const rad = Math.sqrt(1 - y * y)
  const a = i * golden
  return [rad * Math.cos(a), y, rad * Math.sin(a)]
}

function hashD(a: number, b: number) {
  const h = Math.sin(a * 12.9898 + b * 78.233) * 43758.5453
  return h - Math.floor(h)
}

function radiusScale(size: number, pow: number) {
  return (size / 300) ** pow
}

function makeProj(yaw: number, tilt: number, cx: number, cy: number, scale: number) {
  const st = Math.sin(tilt)
  const ct = Math.cos(tilt)
  const sy = Math.sin(yaw)
  const cyw = Math.cos(yaw)
  return (x: number, y: number, z: number) => {
    const x1 = x * cyw + z * sy
    const z1 = -x * sy + z * cyw
    const y1 = y * ct - z1 * st
    const z2 = y * st + z1 * ct
    return [cx + x1 * scale, cy - y1 * scale, z2]
  }
}

/** Accepts `#rgb`, `#rrggbb` or any `r, g, b` triple; falls back to ink. */
export function parseInk(value: string) {
  let hex = (value || "#1f1e1c").trim()
  if (hex[0] === "#") {
    if (hex.length === 4) hex = "#" + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3]
    const packed = parseInt(hex.slice(1, 7), 16)
    if (!Number.isNaN(packed)) {
      return [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255]
    }
  }
  const parts = hex.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/)
  return parts ? [+parts[1], +parts[2], +parts[3]] : [31, 30, 28]
}

// A dot's `white` runs 0 (full ink) to 1 (paper), which is how depth reads.
function paint(ctx: CanvasRenderingContext2D, dots: Dot[], ink: number[], rMin: number) {
  dots.sort((left, right) => left.z - right.z)
  for (const dot of dots) {
    const alpha = dot.a ?? 1
    if (alpha < 0.02) continue
    const w = Math.min(1, Math.max(0, dot.white))
    const r = Math.round(ink[0] + (255 - ink[0]) * w)
    const g = Math.round(ink[1] + (255 - ink[1]) * w)
    const b = Math.round(ink[2] + (255 - ink[2]) * w)
    ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`
    ctx.beginPath()
    ctx.arc(dot.x, dot.y, Math.max(rMin, dot.r), 0, Math.PI * 2)
    ctx.fill()
  }
}

// orbits: particles running tilted great circles — the "working" state.
function drawOrbits(ctx: CanvasRenderingContext2D, size: number, t: number, ink: number[], o: OrbTuning) {
  const cx = size / 2
  const cy = size / 2
  const R = (size / 2) * 0.82
  const pt = makeProj(t * 0.12, 0.3, cx, cy, 1)
  const rs = radiusScale(size, o.rsPow)
  const dots: Dot[] = []
  for (let orb = 0; orb < o.orbitN; orb++) {
    const h1 = hashD(orb, 1.7)
    const h2 = hashD(orb, 5.2)
    const h3 = hashD(orb, 8.9)
    const ro = R * (0.45 + 0.52 * h1)
    const th = h1 * 2 * Math.PI
    const phi = Math.acos(2 * h2 - 1)
    const nx = Math.sin(phi) * Math.cos(th)
    const ny = Math.cos(phi)
    const nz = Math.sin(phi) * Math.sin(th)
    let ux = -ny
    let uy = nx
    const uz = 0
    const ul = Math.max(1e-6, Math.sqrt(ux * ux + uy * uy))
    ux /= ul
    uy /= ul
    const vx = ny * uz - nz * uy
    const vy = nz * ux - nx * uz
    const vz = nx * uy - ny * ux
    const speed = (0.25 + 0.55 * h3) * (h3 > 0.5 ? 1 : -1)
    for (let k = 0; k < o.ghostN; k++) {
      const a = (k / o.ghostN) * 2 * Math.PI
      const [px, py, z] = pt(
        (ux * Math.cos(a) + vx * Math.sin(a)) * ro,
        (uy * Math.cos(a) + vy * Math.sin(a)) * ro,
        (uz * Math.cos(a) + vz * Math.sin(a)) * ro
      )
      const depth = (z / ro + 1) / 2
      dots.push({ x: px, y: py, z, r: o.ghostR * rs, white: 0.72, a: o.ghostA * (0.4 + 0.6 * depth) })
    }
    for (let m = 0; m < o.particles; m++) {
      const a = t * speed + (m / o.particles) * 2 * Math.PI + h2 * 6
      const [px, py, z] = pt(
        (ux * Math.cos(a) + vx * Math.sin(a)) * ro,
        (uy * Math.cos(a) + vy * Math.sin(a)) * ro,
        (uz * Math.cos(a) + vz * Math.sin(a)) * ro
      )
      const depth = (z / ro + 1) / 2
      dots.push({ x: px, y: py, z, r: (o.partR + o.partRDepth * depth) * rs, white: 0.3 - 0.22 * depth })
    }
  }
  paint(ctx, dots, ink, o.rMin)
}

// ring: a face-on dotted circle whose radius undulates — the "breathing" state.
function drawRing(ctx: CanvasRenderingContext2D, size: number, t: number, ink: number[], o: OrbTuning) {
  const cx = size / 2
  const cy = size / 2
  const R = (size / 2) * 0.78
  const spin = o.spin ?? 1
  const camTilt = 0.3
  const pt = makeProj(t * 0.1 * spin, camTilt, cx, cy, 1)
  const rs = radiusScale(size, o.rsPow)
  const dots: Dot[] = []
  for (let i = 0; i < o.ghostN; i++) {
    const d = fibDir(i, o.ghostN)
    const [px, py, z] = pt(d[0] * R, d[1] * R, d[2] * R)
    const depth = (z / R + 1) / 2
    dots.push({ x: px, y: py, z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth })
  }
  const ya = t * 0.24 * spin
  const ta = o.faceOn ? -camTilt : 0.55 + 0.3 * Math.sin(t * 0.18) * spin
  const ux = Math.cos(ya)
  const uy = 0
  const uz = Math.sin(ya)
  const vx = -uz * Math.sin(ta)
  const vy = Math.cos(ta)
  const vz = ux * Math.sin(ta)
  const nx = uy * vz - uz * vy
  const ny = uz * vx - ux * vz
  const nz = ux * vy - uy * vx
  const wobAmp = 0.23 * o.wobMul
  const baseR = o.faceOn ? R / (1 + 0.85 * wobAmp) : R
  const lanes = Math.max(1, Math.round(o.lanes * o.bandMul))
  for (let w = 0; w < lanes; w++) {
    const laneOff = (w - (lanes - 1) / 2) * 0.075
    const edge = Math.abs(w - (lanes - 1) / 2) / Math.max(1, (lanes - 1) / 2)
    for (let k = 0; k < o.segs; k++) {
      const a = (k / o.segs) * 2 * Math.PI
      const wob = (0.16 * Math.sin(a * 3 - t * 1.7 + w * 0.22) + 0.07 * Math.sin(a * 5 + t * 1.1)) * o.wobMul
      const radial = o.faceOn ? 1 + wob : 1
      const off = o.faceOn ? laneOff : laneOff + wob
      const x = ux * Math.cos(a) + vx * Math.sin(a) + nx * off
      const y = uy * Math.cos(a) + vy * Math.sin(a) + ny * off
      const z = uz * Math.cos(a) + vz * Math.sin(a) + nz * off
      const l = Math.sqrt(x * x + y * y + z * z)
      const rr = baseR * radial
      const [px, py, zr] = pt((x / l) * rr, (y / l) * rr, (z / l) * rr)
      const depth = (zr / R + 1) / 2
      dots.push({
        x: px,
        y: py,
        z: zr,
        r: (o.rBase + o.rDepth * depth) * (1 - 0.25 * edge) * rs,
        white: 0.52 - 0.44 * depth + 0.18 * edge,
        a: 0.4 + 0.6 * depth,
      })
    }
  }
  paint(ctx, dots, ink, o.rMin)
}

// rubik: bands twist in quarter turns, scramble → solve — the "solving" state.
function makeMoves(count: number) {
  const moves = []
  for (let i = 0; i < count; i++) {
    const axis = Math.min(2, Math.floor(hashD(i, 2.3) * 3))
    const lo = -1.0 + 0.5 * Math.min(3, Math.floor(hashD(i, 5.9) * 4))
    const dir = hashD(i, 7.7) < 0.5 ? 1 : -1
    moves.push({ axis, lo, hi: lo + 0.5, ang: (dir * Math.PI) / 2 })
  }
  return moves
}

function solveCycle(time: number, count: number, slotDur: number, rest: number) {
  const cyc = 2 * count * slotDur + rest
  const tc = time % cyc
  const amount = new Array<number>(count).fill(0)
  let active = -1
  if (tc < 2 * count * slotDur) {
    const slot = Math.floor(tc / slotDur)
    const p = (tc - slot * slotDur) / slotDur
    const cl = Math.min(1, p / 0.7)
    const ep = 1 - (1 - cl) ** 3
    if (slot < count) {
      for (let i = 0; i < slot; i++) amount[i] = 1
      amount[slot] = ep
      active = slot
    } else {
      const u = 2 * count - 1 - slot
      for (let i = 0; i < u; i++) amount[i] = 1
      amount[u] = 1 - ep
      active = u
    }
  }
  return { amount, active }
}

function applyMoves(p3: number[], moves: ReturnType<typeof makeMoves>, sc: ReturnType<typeof solveCycle>) {
  let [x, y, z] = p3
  let inActive = false
  for (let i = 0; i < moves.length; i++) {
    if (sc.amount[i] <= 0) continue
    const mv = moves[i]
    const coord = mv.axis === 0 ? x : mv.axis === 1 ? y : z
    if (coord < mv.lo || coord >= mv.hi) continue
    if (i === sc.active) inActive = true
    const a = mv.ang * sc.amount[i]
    const ca = Math.cos(a)
    const sa = Math.sin(a)
    if (mv.axis === 0) {
      const y2 = y * ca - z * sa
      z = y * sa + z * ca
      y = y2
    } else if (mv.axis === 1) {
      const x2 = x * ca + z * sa
      z = -x * sa + z * ca
      x = x2
    } else {
      const x2 = x * ca - y * sa
      y = x * sa + y * ca
      x = x2
    }
  }
  return { x, y, z, inActive }
}

function drawRubik(ctx: CanvasRenderingContext2D, size: number, t: number, ink: number[], o: OrbTuning) {
  const cx = size / 2
  const cy = size / 2
  const R = (size / 2) * 0.82
  const pt = makeProj(t * 0.55, 0.35 + 0.1 * Math.sin(t * 0.9), cx, cy, R)
  const rs = radiusScale(size, o.rsPow)
  const moves = makeMoves(o.moveCount)
  const sc = solveCycle(t, o.moveCount, 0.42, 1.2)
  const dots: Dot[] = []
  for (let li = 0; li <= o.latRings; li++) {
    const lat = -Math.PI / 2 + (li / o.latRings) * Math.PI
    const cosLat = Math.cos(lat)
    const sinLat = Math.sin(lat)
    const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * o.lonDensity))
    for (let lj = 0; lj < lonCount; lj++) {
      const lon = (lj / lonCount) * 2 * Math.PI
      const moved = applyMoves([cosLat * Math.cos(lon), sinLat, cosLat * Math.sin(lon)], moves, sc)
      const [px, py, zr] = pt(moved.x, moved.y, moved.z)
      const depth = (zr + 1) / 2
      dots.push({
        x: px,
        y: py,
        z: zr,
        r: (o.rBase + o.rDepth * depth + (moved.inActive ? o.rActive : 0)) * rs,
        white: o.inkFar - o.inkSpan * depth - (moved.inActive ? 0.14 : 0),
      })
    }
  }
  paint(ctx, dots, ink, o.rMin)
}

// morph: a dotted outline cycling circle → triangle → square — "shaping".
const smoothE = (x: number) => x * x * (3 - 2 * x)

function polyPath(verts: number[][]) {
  const V = verts.length
  const L: number[] = []
  let total = 0
  for (let i = 0; i < V; i++) {
    const a = verts[i]
    const b = verts[(i + 1) % V]
    const l = Math.hypot(b[0] - a[0], b[1] - a[1])
    L.push(l)
    total += l
  }
  return (f: number) => {
    let target = f * total
    let i = 0
    while (target > L[i] && i < V - 1) {
      target -= L[i]
      i++
    }
    const a = verts[i]
    const b = verts[(i + 1) % V]
    const ff = L[i] ? Math.min(1, target / L[i]) : 0
    return [a[0] + (b[0] - a[0]) * ff, a[1] + (b[1] - a[1]) * ff]
  }
}

const CIRCLE = (f: number) => {
  const a = -Math.PI / 2 + f * 2 * Math.PI
  return [Math.cos(a) * 0.24, Math.sin(a) * 0.24]
}
const TRIANGLE = polyPath([[0.0, -0.26], [0.24, 0.16], [-0.24, 0.16]])
const SQUARE = polyPath([[0, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2], [-0.2, -0.2]])
const CYCLE = [CIRCLE, TRIANGLE, SQUARE]
const HOLD = 1.4
const MORPH = 0.9
const SEG = HOLD + MORPH

function drawMorph(ctx: CanvasRenderingContext2D, size: number, t: number, ink: number[], o: OrbTuning) {
  const K = CYCLE.length
  const tc = t % (SEG * K)
  const k = Math.floor(tc / SEG)
  const local = tc - k * SEG
  const m = local > HOLD ? smoothE((local - HOLD) / MORPH) : 0
  const sprd = o.spread
  const pA = CYCLE[k]
  const pB = CYCLE[(k + 1) % K]
  const M = 160
  const pts: number[][] = []
  for (let i = 0; i < M; i++) {
    const f = i / M
    const a = pA(f)
    const b = pB(f)
    pts.push([(a[0] + (b[0] - a[0]) * m) * sprd, (a[1] + (b[1] - a[1]) * m) * sprd])
  }
  const L: number[] = []
  let total = 0
  for (let i = 0; i < M; i++) {
    const a = pts[i]
    const b = pts[(i + 1) % M]
    const l = Math.hypot(b[0] - a[0], b[1] - a[1])
    L.push(l)
    total += l
  }
  const n = Math.max(6, Math.round(34 * o.iconD))
  const re = o.rDot * 1.35 * sprd
  const pulse = 1 + 0.02 * Math.sin(local * 3.1)
  const dots: Dot[] = []
  const c2 = size / 2
  let seg = 0
  let acc = 0
  for (let k2 = 0; k2 < n; k2++) {
    const target = (k2 / n) * total
    while (acc + L[seg] < target && seg < M - 1) {
      acc += L[seg]
      seg++
    }
    const a = pts[seg]
    const b = pts[(seg + 1) % M]
    const f = L[seg] ? Math.min(1, (target - acc) / L[seg]) : 0
    const x = (a[0] + (b[0] - a[0]) * f) * pulse
    const y = (a[1] + (b[1] - a[1]) * f) * pulse
    dots.push({ x: c2 + x * size, y: c2 + y * size, z: 0, r: Math.max(0.35, re * size), white: 0.1 })
  }
  paint(ctx, dots, ink, o.rMin)
}

const DRAWS: Record<OrbMode, typeof drawOrbits> = {
  orbits: drawOrbits,
  ring: drawRing,
  rubik: drawRubik,
  morph: drawMorph,
}

/** The preset for a state at a given pixel size. Under 40px uses the small one. */
export function orbOptions(state: OrbState, size: number): OrbOptions {
  const set = PRESETS[state] ?? PRESETS.working
  return { mode: set.mode, tuning: size < 40 ? set.small : set.large }
}

/** Paint one frame. `time` is seconds already multiplied by the effective speed. */
export function drawOrb(ctx: CanvasRenderingContext2D, size: number, time: number, ink: number[], options: OrbOptions) {
  DRAWS[options.mode](ctx, size, time, ink, options.tuning)
}

export const ORB_LABELS: Record<OrbState, string> = {
  working: "Working…",
  breathing: "Thinking…",
  solving: "Solving…",
  shaping: "Shaping…",
}
