/**
 * Auto-generate Vega-Lite chart specifications from Genie query results.
 *
 * Analyses column types returned by the Genie Conversations API and picks
 * the most appropriate chart type:
 *   - temporal + quantitative  → line chart (multi-line if >1 metric)
 *   - nominal  + quantitative  → bar chart  (horizontal when many categories)
 *   - quantitative only        → scatter plot
 *
 * The generated spec uses inline data (capped at 200 rows) and
 * container-responsive width so it renders well inside chat bubbles.
 */

interface Column {
  name: string;
  type_name: string;
}

// ─── Column type classification ──────────────────────────────────────────────

const TEMPORAL_TYPES = new Set([
  'DATE',
  'TIMESTAMP',
  'TIMESTAMP_NTZ',
  'TIMESTAMP_LTZ',
  'DATETIME',
]);

const QUANTITATIVE_TYPES = new Set([
  'INT',
  'INTEGER',
  'BIGINT',
  'LONG',
  'DOUBLE',
  'FLOAT',
  'DECIMAL',
  'NUMERIC',
  'SMALLINT',
  'TINYINT',
  'SHORT',
  'BYTE',
]);

type VegaType = 'temporal' | 'quantitative' | 'nominal';

function classifyColumn(col: Column): VegaType {
  const t = col.type_name.toUpperCase().split('(')[0].trim();
  if (TEMPORAL_TYPES.has(t)) return 'temporal';
  if (QUANTITATIVE_TYPES.has(t)) return 'quantitative';
  return 'nominal';
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Generate a Vega-Lite v5 spec from Genie query-result columns and data.
 * Returns a JSON string suitable for embedding, or `null` when the data
 * shape does not lend itself to a useful chart.
 */
export function generateVegaLiteSpec(
  columns: Column[],
  dataArray: string[][],
): string | null {
  if (!columns || columns.length < 2 || !dataArray || dataArray.length === 0) {
    return null;
  }

  const classified = columns.map((c) => ({
    ...c,
    vegaType: classifyColumn(c) as VegaType,
  }));

  const temporals = classified.filter((c) => c.vegaType === 'temporal');
  const quantitatives = classified.filter((c) => c.vegaType === 'quantitative');
  const nominals = classified.filter((c) => c.vegaType === 'nominal');

  // Build inline data values — cap at 200 rows for rendering performance
  const maxRows = Math.min(dataArray.length, 200);
  const values = dataArray.slice(0, maxRows).map((row) => {
    const obj: Record<string, string | number | null> = {};
    columns.forEach((col, i) => {
      const raw = row[i];
      if (raw === null || raw === undefined || raw === 'null' || raw === '') {
        obj[col.name] = null;
      } else if (classifyColumn(col) === 'quantitative') {
        const num = Number(raw);
        obj[col.name] = Number.isNaN(num) ? null : num;
      } else {
        obj[col.name] = raw;
      }
    });
    return obj;
  });

  let spec: Record<string, unknown> | null = null;

  // ── Case 1: temporal + quantitative(s) → line chart ────────────────────────
  if (temporals.length >= 1 && quantitatives.length >= 1) {
    const xCol = temporals[0];

    if (quantitatives.length === 1) {
      spec = {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: { values },
        mark: { type: 'line', point: true, tooltip: true },
        encoding: {
          x: { field: xCol.name, type: 'temporal', title: xCol.name },
          y: {
            field: quantitatives[0].name,
            type: 'quantitative',
            title: quantitatives[0].name,
          },
          ...(nominals.length >= 1
            ? {
                color: {
                  field: nominals[0].name,
                  type: 'nominal',
                  title: nominals[0].name,
                },
              }
            : {}),
        },
        width: 'container',
        height: 300,
      };
    } else {
      // Multiple quantitative columns → fold into multi-line
      const foldFields = quantitatives.map((q) => q.name);
      spec = {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: { values },
        transform: [{ fold: foldFields, as: ['metric', 'value'] }],
        mark: { type: 'line', point: true, tooltip: true },
        encoding: {
          x: { field: xCol.name, type: 'temporal', title: xCol.name },
          y: { field: 'value', type: 'quantitative', title: 'Value' },
          color: { field: 'metric', type: 'nominal', title: 'Metric' },
        },
        width: 'container',
        height: 300,
      };
    }
  }

  // ── Case 2: nominal + quantitative → bar chart ─────────────────────────────
  else if (nominals.length >= 1 && quantitatives.length >= 1) {
    const xCol = nominals[0];
    const uniqueValues = new Set(values.map((v) => v[xCol.name]));
    const horizontal = uniqueValues.size > 8;

    if (quantitatives.length === 1) {
      const qCol = quantitatives[0];
      spec = {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: { values },
        mark: { type: 'bar', tooltip: true },
        encoding: horizontal
          ? {
              y: {
                field: xCol.name,
                type: 'nominal',
                title: xCol.name,
                sort: '-x',
              },
              x: {
                field: qCol.name,
                type: 'quantitative',
                title: qCol.name,
              },
            }
          : {
              x: { field: xCol.name, type: 'nominal', title: xCol.name },
              y: {
                field: qCol.name,
                type: 'quantitative',
                title: qCol.name,
              },
            },
        width: 'container',
        height: Math.max(300, uniqueValues.size * 25),
      };
    } else {
      // Grouped bar with fold
      const foldFields = quantitatives.map((q) => q.name);
      spec = {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: { values },
        transform: [{ fold: foldFields, as: ['metric', 'value'] }],
        mark: { type: 'bar', tooltip: true },
        encoding: {
          x: { field: xCol.name, type: 'nominal', title: xCol.name },
          y: { field: 'value', type: 'quantitative', title: 'Value' },
          color: { field: 'metric', type: 'nominal', title: 'Metric' },
          xOffset: { field: 'metric' },
        },
        width: 'container',
        height: 300,
      };
    }
  }

  // ── Case 3: only quantitatives → scatter plot ──────────────────────────────
  else if (
    quantitatives.length >= 2 &&
    temporals.length === 0 &&
    nominals.length === 0
  ) {
    spec = {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: { values },
      mark: { type: 'point', tooltip: true, filled: true },
      encoding: {
        x: {
          field: quantitatives[0].name,
          type: 'quantitative',
          title: quantitatives[0].name,
        },
        y: {
          field: quantitatives[1].name,
          type: 'quantitative',
          title: quantitatives[1].name,
        },
        ...(quantitatives.length >= 3
          ? {
              size: {
                field: quantitatives[2].name,
                type: 'quantitative',
              },
            }
          : {}),
      },
      width: 'container',
      height: 300,
    };
  }

  if (!spec) return null;

  // ── Common theme (dark-mode friendly) ──────────────────────────────────────
  spec.autosize = { type: 'fit', contains: 'padding' };
  spec.config = {
    background: 'transparent',
    view: { stroke: 'transparent' },
    axis: {
      labelColor: '#94a3b8',
      titleColor: '#cbd5e1',
      gridColor: '#334155',
      domainColor: '#475569',
      tickColor: '#475569',
    },
    legend: {
      labelColor: '#94a3b8',
      titleColor: '#cbd5e1',
    },
    title: {
      color: '#e2e8f0',
    },
  };

  return JSON.stringify(spec);
}
