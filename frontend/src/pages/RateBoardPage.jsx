// ─── Rate Board Generator Page ────────────────────────────────────────────────
//
// The original three-step flow, unchanged in look and sequence:
//   Upload Image → OCR → Edit Rates → Generate → Download PNG
//
// What is new sits at the end of it: generating now also saves an immutable
// version, and the result step offers "Tampilkan ke Display" alongside the
// downloads that were always there.

import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  Header,
  InfoCards,
  UploadRateImage,
  OCRResultEditor,
  GeneratedDesignPreview,
} from "../components/index.js";
import { ErrorBanner } from "../components/common/ui.jsx";
import { useAuth } from "../hooks/useAuth.js";
import { useRateBoard } from "../hooks/useRateBoard.js";
import { versionApi } from "../services/apiClient.js";

export default function RateBoardPage() {
  const { branches } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const {
    step,
    rates,
    version,
    loading,
    error,
    boardTitle,
    boardSubtitle,
    boardLogoUrl,
    branchId,
    setError,
    setBoardTitle,
    setBoardSubtitle,
    setBoardLogoUrl,
    setBranchId,
    handleOCRResult,
    loadFromVersion,
    generateAndSave,
    handleReset,
  } = useRateBoard();

  // Default to the only branch an account has, so a single-branch staff
  // member is never asked a question with one possible answer.
  useEffect(() => {
    if (branchId === null && branches.length === 1) {
      setBranchId(branches[0].id);
    }
  }, [branches, branchId, setBranchId]);

  // "Open as new version" from the history page lands here.
  useEffect(() => {
    const requestedId = location.state?.openVersionId;
    if (!requestedId) return;

    let cancelled = false;
    versionApi
      .get(requestedId)
      .then((detail) => {
        if (!cancelled) loadFromVersion(detail);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        // Clear the state so a refresh does not reload it again.
        if (!cancelled) navigate(location.pathname, { replace: true, state: {} });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state?.openVersionId]);

  const handleGenerate = async (correctedRates, customization) => {
    try {
      await generateAndSave(correctedRates, {
        ...customization,
        branchId: customization.branchId ?? branchId,
      });
    } catch {
      /* the error is already surfaced through the hook's error state */
    }
  };

  return (
    <div>
      {/* ── Step indicator ───────────────────────────────────────────────── */}
      <Header currentStep={step} />

      {/* ── Page Title ───────────────────────────────────────────────────── */}
      <div style={{ margin: "26px 0 28px", textAlign: "center" }}>
        <h1
          style={{
            fontSize: 28,
            fontWeight: 900,
            color: "#0D47A1",
            marginBottom: 8,
          }}
        >
          Rate Board Generator
        </h1>
        <p style={{ color: "#607D8B", fontSize: 15, margin: 0 }}>
          Upload any rate board image → OCR extracts rates → Edit → Generate
          branded PAM design
        </p>
      </div>

      {/* ── Step Card ────────────────────────────────────────────────────── */}
      <div
        style={{
          background: "#fff",
          borderRadius: 20,
          padding: "36px 40px",
          boxShadow: "0 4px 24px rgba(21,101,192,0.10)",
          border: "1px solid #E3F2FD",
        }}
      >
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {step === 1 && (
          <UploadRateImage
            onResult={handleOCRResult}
            loading={loading}
            setLoading={() => {}}
          />
        )}

        {step === 2 && (
          <OCRResultEditor
            rates={rates}
            onGenerate={handleGenerate}
            loading={loading}
            boardTitle={boardTitle}
            boardSubtitle={boardSubtitle}
            boardLogoUrl={boardLogoUrl}
            onBoardTitleChange={setBoardTitle}
            onBoardSubtitleChange={setBoardSubtitle}
            onBoardLogoChange={setBoardLogoUrl}
            branches={branches}
            branchId={branchId}
            onBranchChange={setBranchId}
          />
        )}

        {step === 3 && version && (
          <GeneratedDesignPreview
            key={version?.id}
            version={version}
            onReset={handleReset}
          />
        )}
      </div>

      {/* ── Info Cards ───────────────────────────────────────────────────── */}
      {step === 1 && <InfoCards />}
    </div>
  );
}
