import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { UseChatHelpers } from '@ai-sdk/react';
import type { ChatMessage } from '@chat-template/core';
import type { VisibilityType } from './visibility-selector';
import { Suggestion } from './elements/suggestion';
import { softNavigateToChatId } from '@/lib/navigation';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { YouLogo } from '@/components/you/you-logo';
import {
  DEFAULT_DEMO_TICKERS,
  loadDemoTickers,
  saveDemoTickers,
} from '@/lib/you-com';
import { cn } from '@/lib/utils';

interface SuggestedActionsProps {
  chatId: string;
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  selectedVisibilityType: VisibilityType;
}

interface SampleQuestion {
  text: string;
  you?: boolean;
}

interface SampleGroup {
  id: string;
  label: string;
  questions: SampleQuestion[];
}

function groupsForTicker(ticker: string): SampleGroup[] {
  return [
    {
      id: 'desk',
      label: 'Filings & data',
      questions: [
        { text: 'How can you help me?' },
        {
          text: `What were ${ticker}'s key revenue highlights in their latest report?`,
        },
        {
          text: `Show a chart of ${ticker} close price over the last month.`,
        },
        {
          text: `Compare ${ticker} with a peer on guidance vs reported results.`,
        },
      ],
    },
    {
      id: 'you',
      label: 'You.com web',
      questions: [
        {
          text: `Search the web for the latest news on ${ticker}.`,
          you: true,
        },
        {
          text: `What are analysts saying about ${ticker} this week?`,
          you: true,
        },
        {
          text: `Research how ${ticker}'s latest filing compares with current coverage.`,
          you: true,
        },
      ],
    },
    {
      id: 'stress',
      label: 'Stress cases',
      questions: [
        {
          text: 'Search Reddit for NVIDIA chip rumors and quote the threads.',
          you: true,
        },
        {
          text: "What does FordDirect's 10-K say its revenue was last year?",
        },
      ],
    },
  ];
}

function PureSuggestedActions({ chatId, sendMessage }: SuggestedActionsProps) {
  const { chatHistoryEnabled } = useAppConfig();
  const [tickers, setTickers] = useState<string[]>(() => loadDemoTickers());
  const [active, setActive] = useState(tickers[0] ?? 'NVDA');

  const groups = useMemo(() => groupsForTicker(active), [active]);

  const send = (suggestion: string) => {
    softNavigateToChatId(chatId, chatHistoryEnabled);
    sendMessage({
      role: 'user',
      parts: [{ type: 'text', text: suggestion }],
    });
  };

  const toggleTicker = (symbol: string) => {
    setActive(symbol);
    if (!tickers.includes(symbol)) {
      const next = [...tickers, symbol].slice(0, 8);
      setTickers(next);
      saveDemoTickers(next);
    }
  };

  return (
    <div
      data-testid="suggested-actions"
      className="flex w-full flex-col gap-3"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground uppercase tracking-wide">
          Universe
        </span>
        {(tickers.length ? tickers : [...DEFAULT_DEMO_TICKERS]).map(
          (symbol) => (
            <button
              key={symbol}
              type="button"
              onClick={() => toggleTicker(symbol)}
              className={cn(
                'rounded-full border px-2 py-0.5 font-medium text-[11px]',
                active === symbol
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-background text-muted-foreground hover:text-foreground',
              )}
            >
              {symbol}
            </button>
          ),
        )}
      </div>

      <div className="grid w-full gap-3 md:grid-cols-3">
        {groups.map((group, gi) => (
          <div key={group.id} className="flex min-w-0 flex-col gap-1.5">
            <p className="flex items-center gap-1.5 font-medium text-[11px] text-muted-foreground uppercase tracking-wide">
              {group.id === 'you' && (
                <YouLogo className="size-3 text-foreground" />
              )}
              {group.label}
            </p>
            {group.questions.map((q, qi) => (
              <motion.div
                key={q.text}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.04 * (gi * 4 + qi) }}
              >
                <Suggestion
                  suggestion={q.text}
                  onClick={send}
                  className="h-auto w-full justify-start whitespace-normal p-2.5 text-left font-normal"
                >
                  <span className="flex items-start gap-1.5">
                    {q.you && (
                      <YouLogo className="mt-0.5 size-3.5 text-foreground" />
                    )}
                    <span>{q.text}</span>
                  </span>
                </Suggestion>
              </motion.div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export const SuggestedActions = PureSuggestedActions;
