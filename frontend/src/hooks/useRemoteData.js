import { useCallback, useEffect, useRef, useState } from "react";
import { startPolling } from "../utils/polling.js";

/** Keep existing content visible while refreshing; cancel obsolete requests. */
export function useRemoteData(fetcher, { initialData = null, refreshMs = 0 } = {}) {
  const [data, setData] = useState(initialData);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const poller = useRef(null);

  useEffect(() => {
    let disposed = false;
    const current = startPolling(async (signal) => {
      setRefreshing(true);
      try {
        const result = await fetcher(signal);
        if (!signal.aborted) {
          setData(result);
          setError(null);
          setLoaded(true);
        }
      } catch (err) {
        if (!signal.aborted) {
          setError(err);
          setLoaded(true);
        }
        throw err;
      } finally {
        if (!disposed) setRefreshing(false);
      }
    }, { intervalMs: refreshMs });
    poller.current = current;
    return () => {
      disposed = true;
      current.stop();
    };
  }, [fetcher, refreshMs]);

  const refresh = useCallback(() => poller.current?.refresh(), []);
  return { data, error, setError, loading: !loaded, refreshing, refresh };
}
