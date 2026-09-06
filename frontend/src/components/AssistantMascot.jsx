/**
 * KAVACH — Assistant mascot
 * =============================
 * Original, abstract badge-and-cap icon — not a likeness of any real
 * person or an attempt to reproduce KSP's actual insignia (the star is
 * a generic four-point mark, not a claimed reproduction of any real
 * crest). Four states driven by plain CSS keyframes on descendant
 * class names, same "orb" idea the write-up describes, just wearing
 * KAVACH's own identity instead of a generic glow:
 *   idle       — slow breathing scale + an occasional blink
 *   listening  — soft concentric rings pulse outward
 *   thinking   — mouth pulses like a loading dot; cap glint sweeps
 *   speaking   — mouth opens/closes in a quick talking rhythm
 */
export default function AssistantMascot({ state = 'idle', size = 40 }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={`ha-mascot ha-mascot--${state}`}
      aria-hidden="true"
    >
      {/* Listening rings — behind everything else */}
      <circle className="ha-mascot-ring ha-mascot-ring-1" cx="32" cy="34" r="22" />
      <circle className="ha-mascot-ring ha-mascot-ring-2" cx="32" cy="34" r="22" />

      <g className="ha-mascot-body">
        {/* Head */}
        <circle cx="32" cy="36" r="18" fill="#0B1D3A" stroke="#C5A028" strokeWidth="1.6" />

        {/* Cap brim */}
        <ellipse cx="32" cy="24.5" rx="17" ry="4.2" fill="#8A6E1A" />
        {/* Cap crown */}
        <path
          d="M17.5 24 Q17 12 32 11 Q47 12 46.5 24 Q39 20 32 20 Q25 20 17.5 24 Z"
          fill="#C5A028"
        />
        {/* Cap band + badge */}
        <rect x="24" y="19.5" width="16" height="4" rx="2" fill="#0B1D3A" />
        <path
          className="ha-mascot-glint"
          d="M30 20 l1.2 2.4 2.6 0.3 -1.9 1.8 0.5 2.5 -2.4 -1.3 -2.4 1.3 0.5 -2.5 -1.9 -1.8 2.6 -0.3 Z"
          fill="#C5A028"
        />

        {/* Eyes */}
        <ellipse className="ha-mascot-eye" cx="26" cy="37" rx="2.1" ry="2.6" fill="#C5A028" />
        <ellipse className="ha-mascot-eye" cx="38" cy="37" rx="2.1" ry="2.6" fill="#C5A028" />

        {/* Mouth */}
        <path className="ha-mascot-mouth" d="M26 45 Q32 49 38 45" fill="none" stroke="#C5A028" strokeWidth="2" strokeLinecap="round" />
      </g>
    </svg>
  )
}
