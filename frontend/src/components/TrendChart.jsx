import { useState } from "react";

const VB_W = 960;
const VB_H = 240;
const BASELINE = 232;
const PLOT_H = 224;
// Separation between fills comes from a non-scaling stroke in the surface colour,
// so it stays 2 device px regardless of how wide the card stretches the viewBox.
const SEGMENT_GAP = 0;
const BAR_GAP = 4;
const MAX_BAR_W = 44;
const CORNER = 4;

function prettyKey(key) {
  return String(key)
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function niceMax(value) {
  if (value <= 1) return 2;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  for (const step of [1, 2, 4, 6, 10]) {
    const candidate = step * magnitude;
    if (candidate >= value) return candidate;
  }
  return 10 * magnitude;
}

function cappedBar(x, y, w, h, r) {
  const rx = Math.min(r, w / 2);
  const ry = Math.min(r, h);
  return [
    `M${x} ${y + h}`,
    `L${x} ${y + ry}`,
    `Q${x} ${y} ${x + rx} ${y}`,
    `L${x + w - rx} ${y}`,
    `Q${x + w} ${y} ${x + w} ${y + ry}`,
    `L${x + w} ${y + h}`,
    "Z",
  ].join(" ");
}

export default function TrendChart({
  buckets = [],
  series = [],
  colors = [],
  unit = "events",
  emptyMessage = "Nothing recorded in this window yet.",
}) {
  // Hover is tied to the identity of the bucket grid, so switching Hourly/Weekly
  // drops a stale highlight instead of pointing it at a different bucket.
  const gridKey = `${buckets.length}:${buckets[0] ? buckets[0].start : ""}`;
  const [hoverState, setHoverState] = useState({ key: gridKey, index: null });
  const hover = hoverState.key === gridKey ? hoverState.index : null;
  const setHover = (index) => setHoverState({ key: gridKey, index });

  const peak = buckets.reduce((acc, b) => Math.max(acc, Number(b.total) || 0), 0);

  if (buckets.length === 0 || peak === 0) {
    return <p className="empty-note">{emptyMessage}</p>;
  }

  const colorByKey = {};
  series.forEach((key, i) => {
    colorByKey[key] = colors[i] || "var(--viz-muted)";
  });

  const scaleMax = niceMax(peak);
  const ticks = [scaleMax, scaleMax / 2, 0];
  const band = VB_W / buckets.length;
  const barW = Math.min(band - BAR_GAP, MAX_BAR_W);
  const labelStep = buckets.length > 12 ? 4 : 1;
  const yFor = (value) => BASELINE - (value / scaleMax) * PLOT_H;
  const hairline = (value) => Math.round(yFor(value)) + 0.5;

  const bars = buckets.map((bucket, i) => {
    const counts = bucket.counts || {};
    const total = Number(bucket.total) || 0;
    const fullH = (total / scaleMax) * PLOT_H;
    const present = series.filter((key) => (counts[key] || 0) > 0);
    const gapTotal = Math.max(0, present.length - 1) * SEGMENT_GAP;
    const roomy = fullH > gapTotal;
    const usable = roomy ? fullH - gapTotal : fullH;
    const gap = roomy ? SEGMENT_GAP : 0;

    let cursor = BASELINE;
    const segments = present.map((key, n) => {
      const h = total > 0 ? (counts[key] / total) * usable : 0;
      cursor -= h;
      const segment = { key, y: cursor, h, capped: n === present.length - 1 };
      cursor -= gap;
      return segment;
    });

    return { x: i * band + (band - barW) / 2, segments };
  });

  const hovered = hover === null ? null : buckets[hover];
  const tipLeft = hover === null ? 0 : ((hover * band + band / 2) / VB_W) * 100;
  const tipShift = tipLeft < 14 ? "0%" : tipLeft > 86 ? "-100%" : "-50%";

  return (
    <div className="trend-chart">
      <div className="trend-plot">
        <div className="trend-yaxis">
          <span className="trend-ytick-ghost">{scaleMax}</span>
          {ticks.map((tick) => (
            <span
              className="trend-ytick"
              key={tick}
              style={{ bottom: `${((VB_H - yFor(tick)) / VB_H) * 100}%` }}
            >
              {tick}
            </span>
          ))}
        </div>

        <div className="trend-canvas" onMouseLeave={() => setHover(null)}>
          <svg
            className="trend-svg"
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`Stacked bar chart of ${unit} across ${buckets.length} intervals, peak ${peak}`}
          >
            {ticks
              .filter((tick) => tick > 0)
              .map((tick) => (
                <line
                  className="trend-grid"
                  key={tick}
                  x1="0"
                  x2={VB_W}
                  y1={hairline(tick)}
                  y2={hairline(tick)}
                />
              ))}

            {hover !== null && (
              <rect className="trend-hover-band" x={hover * band} y="0" width={band} height={VB_H} />
            )}

            {bars.map((bar, i) => (
              <g key={buckets[i].start ?? i}>
                {bar.segments.map((segment) =>
                  segment.capped ? (
                    <path
                      key={segment.key}
                      className="trend-seg"
                      d={cappedBar(bar.x, segment.y, barW, segment.h, CORNER)}
                      fill={colorByKey[segment.key]}
                    />
                  ) : (
                    <rect
                      key={segment.key}
                      className="trend-seg"
                      x={bar.x}
                      y={segment.y}
                      width={barW}
                      height={segment.h}
                      fill={colorByKey[segment.key]}
                    />
                  )
                )}
              </g>
            ))}

            <line className="trend-baseline" x1="0" x2={VB_W} y1={BASELINE + 0.5} y2={BASELINE + 0.5} />

            {buckets.map((bucket, i) => (
              <rect
                className="trend-hit"
                key={bucket.start ?? i}
                x={i * band}
                y="0"
                width={band}
                height={VB_H}
                onMouseEnter={() => setHover(i)}
              />
            ))}
          </svg>

          {hovered && (
            <div
              className="trend-tooltip"
              style={{ left: `${tipLeft}%`, transform: `translateX(${tipShift})` }}
            >
              <div className="trend-tip-label">{hovered.label}</div>
              {series.map((key) => (
                <div className="trend-tip-row" key={key}>
                  <span className="trend-tip-key" style={{ background: colorByKey[key] }} />
                  <span className="trend-tip-name">{prettyKey(key)}</span>
                  <span className="trend-tip-value">{(hovered.counts || {})[key] || 0}</span>
                </div>
              ))}
              <div className="trend-tip-total">
                <span>Total</span>
                <span>
                  {hovered.total || 0} {unit}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="trend-xaxis">
          {buckets.map((bucket, i) => (
            <span className="trend-xtick" key={bucket.start ?? i}>
              {(buckets.length - 1 - i) % labelStep === 0 ? bucket.label : ""}
            </span>
          ))}
        </div>
      </div>

      <div className="trend-legend">
        {series.map((key) => (
          <span className="trend-legend-item" key={key}>
            <span className="trend-swatch" style={{ background: colorByKey[key] }} />
            {prettyKey(key)}
          </span>
        ))}
      </div>

      <table className="trend-sr-table">
        <caption>{`${prettyKey(unit)} per interval`}</caption>
        <tbody>
          <tr>
            <th scope="col">Interval</th>
            {series.map((key) => (
              <th scope="col" key={key}>
                {prettyKey(key)}
              </th>
            ))}
            <th scope="col">Total</th>
          </tr>
          {buckets.map((bucket, i) => (
            <tr key={bucket.start ?? i}>
              <th scope="row">{bucket.label}</th>
              {series.map((key) => (
                <td key={key}>{(bucket.counts || {})[key] || 0}</td>
              ))}
              <td>{bucket.total || 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
