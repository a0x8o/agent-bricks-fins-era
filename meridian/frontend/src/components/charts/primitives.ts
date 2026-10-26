/** Custom series primitives — canvas-drawn visuals that DOM overlays can't do.
 *  BandFill: shaded region between two price lines (Bollinger/Envelope/channel).
 */

import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";

interface Pt {
  time: Time;
  upper: number;
  lower: number;
}

class BandFillRenderer implements IPrimitivePaneRenderer {
  constructor(
    private pts: Pt[],
    private color: string,
    private ctx: { chart: any; series: any },
  ) {}

  draw(target: any) {
    const { chart, series } = this.ctx;
    if (!chart || !series || !this.pts.length) return;
    target.useMediaCoordinateSpace(({ context: ctx }: { context: CanvasRenderingContext2D }) => {
      ctx.save();
      ctx.globalAlpha = 0.14;
      ctx.fillStyle = this.color;
      ctx.beginPath();
      let started = false;
      for (const p of this.pts) {
        const x = chart.timeScale().timeToCoordinate(p.time);
        const y = series.priceToCoordinate(p.upper);
        if (x == null || y == null) continue;
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else ctx.lineTo(x, y);
      }
      for (let i = this.pts.length - 1; i >= 0; i--) {
        const p = this.pts[i];
        const x = chart.timeScale().timeToCoordinate(p.time);
        const y = series.priceToCoordinate(p.lower);
        if (x == null || y == null) continue;
        ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    });
  }
}

export class BandFillPrimitive implements ISeriesPrimitive {
  private _view: IPrimitivePaneView;

  constructor(points: Pt[], color: string) {
    const renderer = new BandFillRenderer(points, color, { chart: null, series: null });
    const prim = this;
    this._view = {
      renderer: () => renderer,
      zOrder: () => "bottom" as const,
    };
    (this as any)._renderer = renderer;
    void prim;
  }

  attached(param: SeriesAttachedParameter<Time>) {
    (this as any)._renderer.ctx.chart = param.chart;
    (this as any)._renderer.ctx.series = param.series;
  }

  paneViews() {
    return [this._view];
  }
}
