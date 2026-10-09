import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart3,
  BookOpenText,
  Database,
  Sparkles,
} from 'lucide-react';
import { YouLogo } from '@/components/you/you-logo';

interface AgentDef {
  id: string;
  label: string;
  icon: typeof Database;
  caption: string;
  you?: boolean;
}

const AGENTS: AgentDef[] = [
  {
    id: 'ka',
    label: 'Knowledge Assistant',
    icon: BookOpenText,
    caption: 'Reading 10-K & 10-Q filings and earnings releases…',
  },
  {
    id: 'genie',
    label: 'Genie · SQL',
    icon: Database,
    caption: 'Querying governed ticker tables…',
  },
  {
    id: 'charts',
    label: 'Visualization',
    icon: BarChart3,
    caption: 'Composing a chart from the results…',
  },
  {
    id: 'web',
    label: 'You.com',
    icon: Database,
    caption: 'Searching live web and news via You.com…',
    you: true,
  },
];

const FINAL_CAPTION = 'Synthesizing the answer…';

/**
 * Animated multi-agent "thinking" indicator shown while the supervisor works.
 * Cycles a highlight across the child agents with a rotating caption and a
 * shimmer skeleton, so a long-running query feels responsive.
 */
export function AgentActivity() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setActive((i) => (i + 1) % (AGENTS.length + 1));
    }, 1900);
    return () => clearInterval(interval);
  }, []);

  const caption =
    active >= AGENTS.length ? FINAL_CAPTION : AGENTS[active].caption;

  return (
    <div
      className="w-full rounded-xl border bg-card/60 p-3"
      role="status"
      aria-live="polite"
      data-testid="agent-activity"
    >
      <div className="mb-3 flex items-center gap-2">
        <motion.div
          animate={{ rotate: [0, 8, -8, 0] }}
          transition={{
            duration: 2,
            repeat: Number.POSITIVE_INFINITY,
            ease: 'easeInOut',
          }}
          className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary"
        >
          <Sparkles className="h-3.5 w-3.5" />
        </motion.div>
        <span className="font-medium text-sm">
          Coordinating specialist agents
        </span>
      </div>

      {/* Agent pipeline */}
      <div className="flex flex-wrap items-stretch gap-1.5">
        {AGENTS.map((agent, i) => {
          const Icon = agent.icon;
          const isActive = i === active;
          return (
            <motion.div
              key={agent.id}
              animate={{
                scale: isActive ? 1.02 : 1,
                opacity: isActive ? 1 : 0.55,
              }}
              transition={{ duration: 0.3 }}
              className={[
                'flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs',
                isActive
                  ? 'border-primary/40 bg-primary/5 text-foreground'
                  : 'border-transparent bg-muted/50 text-muted-foreground',
              ].join(' ')}
            >
              {agent.you ? (
                <YouLogo className="h-3.5 w-3.5 text-foreground" />
              ) : (
                <Icon className="h-3.5 w-3.5" />
              )}
              <span className="whitespace-nowrap">{agent.label}</span>
              {isActive && (
                <motion.span
                  className="ml-0.5 h-1.5 w-1.5 rounded-full bg-primary"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{
                    duration: 1,
                    repeat: Number.POSITIVE_INFINITY,
                  }}
                />
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Rotating caption */}
      <motion.p
        key={caption}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="mt-3 text-muted-foreground text-xs"
      >
        {caption}
      </motion.p>

      {/* Shimmer skeleton */}
      <div className="mt-3 space-y-1.5">
        {[88, 72, 60].map((w) => (
          <div
            key={w}
            className="relative h-2 overflow-hidden rounded bg-muted"
            style={{ width: `${w}%` }}
          >
            <motion.div
              className="absolute inset-0"
              style={{
                background:
                  'linear-gradient(90deg, transparent, hsl(var(--foreground) / 0.08), transparent)',
              }}
              animate={{ x: ['-100%', '100%'] }}
              transition={{
                duration: 1.6,
                repeat: Number.POSITIVE_INFINITY,
                ease: 'linear',
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
