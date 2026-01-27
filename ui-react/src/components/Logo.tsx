export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Mining chip/circuit board background */}
      <rect x="10" y="10" width="80" height="80" rx="8" fill="currentColor" fillOpacity="0.1" />
      
      {/* Circuit traces */}
      <path
        d="M20 30 H40 M60 30 H80 M20 50 H35 M65 50 H80 M20 70 H40 M60 70 H80"
        stroke="currentColor"
        strokeWidth="2"
        strokeOpacity="0.3"
      />
      
      {/* Central hashrate symbol (stylized H) */}
      <path
        d="M35 35 V65 M35 50 H65 M65 35 V65"
        stroke="currentColor"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      
      {/* Mining picks crossed */}
      <path
        d="M40 40 L30 30 M60 40 L70 30"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeOpacity="0.6"
      />
      
      {/* Small dots (connection points) */}
      <circle cx="20" cy="30" r="2" fill="currentColor" fillOpacity="0.5" />
      <circle cx="80" cy="30" r="2" fill="currentColor" fillOpacity="0.5" />
      <circle cx="20" cy="50" r="2" fill="currentColor" fillOpacity="0.5" />
      <circle cx="80" cy="50" r="2" fill="currentColor" fillOpacity="0.5" />
      <circle cx="20" cy="70" r="2" fill="currentColor" fillOpacity="0.5" />
      <circle cx="80" cy="70" r="2" fill="currentColor" fillOpacity="0.5" />
    </svg>
  )
}
