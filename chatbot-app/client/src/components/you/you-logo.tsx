import { cn } from '@/lib/utils';

/**
 * You.com mark. The live-web signal in this app — used on tools, citations,
 * sample questions, and the "Powered by You.com" lockup.
 *
 * Drawn as a rounded square with a geometric Y so it stays legible at 12px
 * and 28px. currentColor so it follows the surrounding text.
 */
export function YouLogo({
  className,
  title = 'You.com',
}: {
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      role="img"
      aria-label={title}
      className={cn('shrink-0', className)}
    >
      <title>{title}</title>
      <rect
        x="1.5"
        y="1.5"
        width="21"
        height="21"
        rx="6"
        fill="currentColor"
      />
      <path
        d="M7.4 6.8h2.35l2.25 5.35 2.25-5.35H16.6L12.7 16.4h-1.4L7.4 6.8Z"
        fill="var(--you-on-mark, #fff)"
      />
    </svg>
  );
}

export function PoweredByYou({ className }: { className?: string }) {
  return (
    <a
      href="https://you.com"
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'inline-flex items-center gap-1.5 text-muted-foreground text-xs hover:text-foreground',
        className,
      )}
    >
      <YouLogo className="size-3.5 text-foreground" />
      <span>
        Powered by <span className="font-medium text-foreground">You.com</span>
      </span>
    </a>
  );
}
