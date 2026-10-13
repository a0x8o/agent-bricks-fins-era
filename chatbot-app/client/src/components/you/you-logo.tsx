import { cn } from '@/lib/utils';

/**
 * Official You.com mark (gradient hexagon with the four-point star). The
 * live-web signal in this app — used on tools, citations, sample questions,
 * and the "Powered by You.com" lockup.
 *
 * Assets in client/public come from the You.com brand files (img/logo-*.png).
 * The mark carries its own brand colour, so any text-* class passed in is
 * inert; size it with size-* / h-* w-*.
 */
export function YouLogo({
  className,
  title = 'You.com',
}: {
  className?: string;
  title?: string;
}) {
  return (
    <img
      src="/you-mark.png"
      alt={title}
      title={title}
      draggable={false}
      className={cn('shrink-0 object-contain', className)}
    />
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
      <span>Powered by</span>
      {/* Black wordmark on light themes, white on dark. */}
      <img
        src="/you-lockup.png"
        alt="You.com"
        draggable={false}
        className="h-3.5 w-auto dark:hidden"
      />
      <img
        src="/you-lockup-white.png"
        alt="You.com"
        draggable={false}
        className="hidden h-3.5 w-auto dark:block"
      />
    </a>
  );
}
