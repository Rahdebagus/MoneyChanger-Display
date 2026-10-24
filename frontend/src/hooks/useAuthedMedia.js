import { useEffect, useState } from "react";
import { fetchMediaBlob } from "../services/apiClient.js";

/** Abort obsolete downloads and release each object URL with its effect. */
export function useAuthedMedia(path) {
  const [result, setResult] = useState({ path: null, url: null, error: null });

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    let objectUrl;
    fetchMediaBlob(path, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setResult({ path, url: objectUrl, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ path, url: null, error });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  const current = path && result.path === path;
  return {
    url: current ? result.url : null,
    error: current ? result.error : null,
    loading: Boolean(path && !current),
  };
}
