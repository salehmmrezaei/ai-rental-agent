import { useRef, useState } from "react";
export function useAction() {
  const lock = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  async function run<T>(
    operation: () => Promise<T>,
    message?: string,
  ): Promise<T | undefined> {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await operation();
      if (message) setSuccess(message);
      return result;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Operation failed. Please try again.",
      );
      return undefined;
    } finally {
      lock.current = false;
      setPending(false);
    }
  }
  return {
    run,
    pending,
    error,
    success,
    reset: () => {
      setError(null);
      setSuccess(null);
    },
  };
}
