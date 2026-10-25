/** Pinned insights — user-pinned Genie answer cards. localStorage now,
 *  Delta persistence behind FEATURE_PERSISTENCE later. */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChartSpec } from "../lib/genie";

export interface PinnedInsight {
  id: string;
  title: string;
  question: string;
  sql: string | null;
  chartSpec: ChartSpec | null;
  createdAt: string;
}

interface PinState {
  pins: PinnedInsight[];
  pin: (p: Omit<PinnedInsight, "id" | "createdAt">) => void;
  unpin: (id: string) => void;
  rename: (id: string, title: string) => void;
  reorder: (from: number, to: number) => void;
}

export const usePins = create<PinState>()(
  persist(
    (set) => ({
      pins: [],
      pin: (p) =>
        set((s) => ({
          pins: [...s.pins, { ...p, id: crypto.randomUUID(), createdAt: new Date().toISOString() }],
        })),
      unpin: (id) => set((s) => ({ pins: s.pins.filter((p) => p.id !== id) })),
      rename: (id, title) =>
        set((s) => ({ pins: s.pins.map((p) => (p.id === id ? { ...p, title } : p)) })),
      reorder: (from, to) =>
        set((s) => {
          const pins = [...s.pins];
          const [x] = pins.splice(from, 1);
          pins.splice(to, 0, x);
          return { pins };
        }),
    }),
    { name: "meridian-pins" },
  ),
);
