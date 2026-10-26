import { coinSuffixes, presentCopper, type MoneyKind } from "../features/market/currency";

export function MoneyValue({ value, kind = "observed", compact = false }: { value: string | number; kind?: MoneyKind; compact?: boolean }) {
  const amount = presentCopper(value, kind);
  return <div className={`exact-value money-value${compact ? " money-compact" : ""}`}>
    <span className="coin-amount" role="img" aria-label={`${amount.label}${amount.rounded ? compact ? `; valor exacto ${amount.original} copper` : "; redondeo visual a 1 copper, valor original en el detalle técnico" : ""}`}>
      {amount.rounded && <span aria-hidden="true">≈</span>}
      {amount.negative && <span className="coin-sign" aria-hidden="true">−</span>}
      {amount.tokens.map(token => <span className={`coin-denomination coin-${token.denomination}`} key={token.denomination} aria-hidden="true">
        <i/><span>{token.value}<small>{coinSuffixes[token.denomination]}</small></span>
      </span>)}
    </span>
    {amount.rounded && !compact && <span className="currency-fraction-note">Redondeo visual a 1 copper · ROUND_HALF_UP</span>}
    {!compact && <details><summary>{amount.rounded ? "Ver valor exacto · sin redondeo" : "Ver valor exacto en copper"}</summary>
      <p>Original: <span className="raw-copper">{amount.original}</span> copper</p>
    </details>}
  </div>;
}
