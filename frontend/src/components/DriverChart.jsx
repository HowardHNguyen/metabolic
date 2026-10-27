import React from "react";

export default function DriverChart({ contributions, maxRows = 8 }) {
  if (!contributions || contributions.length === 0) return null;

  const rows = contributions.slice(0, maxRows);
  const max = Math.max(...rows.map((c) => Math.abs(c.value)), 0.0001);

  return (
    <div className="driver-chart">
      <h3>What's driving your result</h3>
      <p className="driver-chart-sub">
        Top factors by impact, compared to a healthy baseline. Red increases predicted likelihood;
        green decreases it.
      </p>
      <div className="driver-rows">
        {rows.map((c) => {
          const pct = (Math.abs(c.value) / max) * 50;
          const positive = c.value >= 0;
          return (
            <div className="driver-row" key={c.feature}>
              <div className="driver-label">{c.friendly_name || c.feature}</div>
              <div className="driver-track">
                <div className="driver-center-line" />
                <div
                  className={`driver-bar ${positive ? "up" : "down"}`}
                  style={{
                    width: `${Math.max(pct, 1.5)}%`,
                    left: positive ? "50%" : undefined,
                    right: positive ? undefined : "50%",
                  }}
                />
              </div>
              <div className={`driver-value ${positive ? "up" : "down"}`}>
                {positive ? "+" : ""}
                {(c.value * 100).toFixed(1)}pp
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
