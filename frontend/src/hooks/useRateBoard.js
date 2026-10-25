// Save rates and receive the finished PNG in the same request.
import { useCallback, useEffect, useRef, useState } from "react";

import { APP_COMPANY } from "../constants/currencies.js";
import { versionApi } from "../services/apiClient.js";

import { createSaveRequest } from "../utils/saveRequest.js";

export const useRateBoard = () => {
  const [step, setStep] = useState(1);
  const [rates, setRates] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [version, setVersion] = useState(null);
  const [sourceVersionId, setSourceVersionId] = useState(null);

  const [boardTitle, setBoardTitle] = useState("MONEY CHANGER");
  const [boardSubtitle, setBoardSubtitle] = useState(APP_COMPANY);
  const [boardLogoUrl, setBoardLogoUrl] = useState(null);
  const [branchId, setBranchId] = useState(null);

  const [saver] = useState(() => createSaveRequest(versionApi.create));
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; saver.cancel(); };
  }, [saver]);

  const handleOCRResult = useCallback((extractedRates) => {
    setRates(extractedRates || {});
    setError(null);
    setStep(2);
  }, []);

  /** Load an existing version into the editor as the basis for a new one. */
  const loadFromVersion = useCallback((detail) => {
    saver.reset();
    setRates(detail.rates || {});
    setBoardTitle(detail.board_title || "MONEY CHANGER");
    setBoardSubtitle(detail.board_subtitle || APP_COMPANY);
    setBranchId(detail.branch_id ?? null);
    setSourceVersionId(detail.id);
    setVersion(null);
    setError(null);
    setStep(2);
  }, [saver]);

  const generateAndSave = useCallback(
    async (correctedRates, customization) => {
      setLoading(true);
      setError(null);

      try {
        const detail = await saver.save({
          rates: correctedRates,
          title: customization.title,
          subtitle: customization.subtitle,
          logo_base64: customization.logoUrl || null,
          branch_id: customization.branchId ?? null,
          source_version_id: sourceVersionId,
        });

        if (mounted.current) { setVersion(detail); setStep(3); }
        return detail;
      } catch (err) {
        if (mounted.current) setError(err);
        throw err;
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [sourceVersionId, saver]
  );

  const handleReset = useCallback(() => {
    saver.reset();
    setStep(1);
    setRates({});
    setVersion(null);
    setSourceVersionId(null);
    setLoading(false);
    setError(null);
  }, [saver]);

  return {
    step,
    rates,
    version,
    loading,
    error,
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
