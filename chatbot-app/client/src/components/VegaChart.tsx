'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Vega } from 'react-vega';

interface VegaChartProps {
  specString: string;
}

export function VegaChart({ specString }: VegaChartProps) {
  const spec = useMemo(() => {
    try {
      // 1. First pass parsing
      let parsed = typeof specString === 'string' ? JSON.parse(specString) : specString;

      // 2. Handle Databricks Agent "wrapper" format
      // The output often looks like: { "rows": [ [ "{\"actual_spec\": ...}" ] ] }
      if (parsed && parsed.rows && Array.isArray(parsed.rows)) {
        const firstRow = parsed.rows[0];
        if (Array.isArray(firstRow) && firstRow.length > 0) {
          const innerContent = firstRow[0];
          // If the inner content is a stringified JSON, parse it again
          if (typeof innerContent === 'string') {
            try {
              return JSON.parse(innerContent);
            } catch (e) {
              console.warn("Found wrapper but failed to parse inner JSON", e);
            }
          }
        }
      }

      return parsed;
    } catch (e) {
      console.error("Failed to parse Vega spec:", e);
      return null;
    }
  }, [specString]);

  // react-vega renders `width: 'container'` as a zero-width, invisible chart.
  // Measure the wrapper and substitute pixels (same fix as DataExplorerView).
  const wantsContainer = spec?.width === 'container';
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || !wantsContainer) return;
    const update = () => {
      if (el.clientWidth > 0) setWidth(el.clientWidth - 32); // p-4 padding
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [wantsContainer]);
  const sized = useMemo(
    () =>
      wantsContainer ? { ...spec, width: Math.max(width, 200) } : spec,
    [spec, wantsContainer, width],
  );

  if (!spec || !spec.$schema) {
    return (
      <div className="p-2 text-xs text-red-400 bg-red-50 border border-red-100 rounded">
        Invalid Chart Data
      </div>
    );
  }

  return (
    <div ref={ref} className="w-full my-4 p-4 bg-white rounded-lg shadow-sm border border-gray-200 overflow-x-auto">
      {(!wantsContainer || width > 0) && <Vega spec={sized} actions={true} />}
    </div>
  );
}