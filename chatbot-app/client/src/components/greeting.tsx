import { motion } from 'framer-motion';
import { PoweredByYou } from '@/components/you/you-logo';

export const Greeting = () => {
  return (
    <div
      key="overview"
      className="mx-auto mt-4 flex size-full max-w-3xl flex-col justify-center px-4 md:mt-10 md:px-8"
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.35 }}
        className="font-semibold text-xl md:text-2xl"
      >
        Cross-industry financial research
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.45 }}
        className="mt-1 text-muted-foreground text-base md:text-lg"
      >
        Filings and governed tables in Databricks. Live web and news through
        You.com.
      </motion.div>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.55 }}
        className="mt-3"
      >
        <PoweredByYou />
      </motion.div>
    </div>
  );
};
