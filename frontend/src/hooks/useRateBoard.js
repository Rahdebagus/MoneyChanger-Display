// ─── Rate Board State Hook ────────────────────────────────────────────────────
//
// Drives the three-step generator flow. "Generate" now creates a saved,
// immutable version and queues the render job; the preview shows the media
// the worker produced. Saving never changes what a TV is showing - that only
// happens on an explicit publish.

import { useCallback, useEffect, useRef, useState } from "react";

import { APP_COMPANY } from "../constants/currencies.js";
import { jobApi, versionApi } from "../services/apiClient.js";

const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 180000;

export const useRateBoard = () => {
  const [step, setStep] = useState(1);
  const [rates, setRates] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(0);

  const [version, setVersion] = useState(null);
  const [sourceVersionId, setSourceVersionId] = useState(null);

  const [boardTitle, setBoardTitle] = useState("MONEY CHANGER");
  const [boardSubtitle, setBoardSubtitle] = useState(APP_COMPANY);
  const [boardLogoUrl, setBoardLogoUrl] = useState(null);
  const [branchId, setBranchId] = useState(null);

  const pollTimer = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const handleOCRResult = useCallback((extractedRates) => {
    setRates(extractedRates || {});
    setError(null);
    setStep(2);
  }, []);

  /** Load an existing version into the editor as the basis for a new one. */
  const loadFromVersion = useCallback((detail) => {
    setRates(detail.rates || {});
    setBoardTitle(detail.board_title || "MONEY CHANGER");
    setBoardSubtitle(detail.board_subtitle || APP_COMPANY);
    setBranchId(detail.branch_id ?? null);
    setSourceVersionId(detail.id);
    setVersion(null);
    setError(null);
    setStep(2);
  }, []);

  /** Poll a generate job until the version is ready or the job fails. */
  const waitForJob = useCallback(
    (jobId, versionId) =>
      new Promise((resolve, reject) => {
        const startedAt = Date.now();

        const tick = async () => {
          try {
            const job = await jobApi.get(jobId);
            setProgress(job.progress ?? 0);

            if (job.status === "succeeded") {
              const detail = await versionApi.get(versionId);
              resolve(detail);
              return;
            }

            if (job.status === "failed" || job.status === "cancelled") {
              reject(
                new Error(
                  job.error_message
                    ? "Pembuatan board gagal. Silakan coba lagi."
                    : "Pembuatan board gagal."
                )
              );
              return;
            }

            if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
              reject(new Error("Pembuatan board terlalu lama. Cek status di Dashboard."));
              return;
            }

            pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
          } catch (err) {
            reject(err);
          }
        };

        tick();
      }),
    []
  );

  const generateAndSave = useCallback(
    async (correctedRates, customization) => {
      setLoading(true);
      setError(null);
      setProgress(0);

      try {
        const response = await versionApi.create({
          rates: correctedRates,
          title: customization.title,
          subtitle: customization.subtitle,
          logo_base64: customization.logoUrl || null,
          branch_id: customization.branchId ?? null,
          source_version_id: sourceVersionId,
        });

        const detail = await waitForJob(response.job.id, response.version.id);
        setVersion(detail);
        setStep(3);
        return detail;
      } catch (err) {
        setError(err);
        throw err;
      } finally {
        setLoading(false);
        stopPolling();
      }
    },
    [sourceVersionId, waitForJob, stopPolling]
  );

  const handleReset = useCallback(() => {
    stopPolling();
    setStep(1);
    setRates({});
    setVersion(null);
    setSourceVersionId(null);
    setLoading(false);
    setError(null);
    setProgress(0);
  }, [stopPolling]);

  return {
    step,
    rates,
    version,
    loading,
    error,
    progress,
    boardTitle,
    boardSubtitle,
    boardLogoUrl,
    branchId,
    sourceVersionId,
    setStep,
    setLoading,
    setError,
    setBoardTitle,
    setBoardSubtitle,
    setBoardLogoUrl,
    setBranchId,
    setVersion,
    handleOCRResult,
    loadFromVersion,
    generateAndSave,
    handleReset,
  };
};
