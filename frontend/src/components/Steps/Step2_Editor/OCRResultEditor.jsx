// ─── OCR Result Editor Component ───────────────────────────────────────────────

import { useRef, useState } from 'react';
import { ALL_CURRENCIES, LEFT_COL, RIGHT_COL, APP_COMPANY } from '../../../constants/currencies.js';
import { CurrencyInput } from './CurrencyInput.jsx';
import { DerivedValuesBox } from './DerivedValuesBox.jsx';

export function OCRResultEditor({
  rates, onGenerate, loading,
  boardTitle, boardSubtitle, boardLogoUrl,
  onBoardTitleChange, onBoardSubtitleChange, onBoardLogoChange,
  branches = [], branchId, onBranchChange,
}) {
  const [values, setValues] = useState(() => {
    // The API speaks USD_T / USD_K; the editor fields are USDT / USDK.
    // A null value means "not traded" and must stay an empty field, never 0.
    const incoming = { ...(rates || {}) };
    if (incoming.USD_T !== undefined) incoming.USDT = incoming.USD_T;
    if (incoming.USD_K !== undefined) incoming.USDK = incoming.USD_K;

    const init = {};
    ALL_CURRENCIES.forEach((c) => {
      const value = incoming[c];
      init[c] = value === null || value === undefined ? '' : String(value);
    });
    return init;
  });
  const [error, setError] = useState(null);
  const logoInputRef = useRef(null);

  const usdVal = parseFloat(values['USD']) || 0;

  const handleChange = (code, val) => {
    setValues((prev) => ({ ...prev, [code]: val }));
  };

  const handleLogoUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => onBoardLogoChange(evt.target.result);
    reader.readAsDataURL(file);
  };

  const handleGenerate = () => {
    const payload = {};
    let hasAny = false;
    let invalid = null;

    // Values travel as strings so the server keeps the exact decimal. An
    // empty field is sent as null, which the board renders as "-" rather
    // than as a rate of zero.
    const put = (apiCode, raw) => {
      const text = String(raw ?? '').trim();
      if (text === '') {
        payload[apiCode] = null;
        return;
      }
      const numeric = Number(text);
      if (!Number.isFinite(numeric) || numeric < 0) {
        invalid = apiCode;
        return;
      }
      payload[apiCode] = text;
      if (numeric > 0) hasAny = true;
    };

    ALL_CURRENCIES.forEach((code) => {
      if (code === 'USDT' || code === 'USDK') return;
      put(code, values[code]);
    });
    put('USD_T', values['USDT']);
    put('USD_K', values['USDK']);

    if (invalid) {
      setError(`Nilai ${invalid} tidak valid. Gunakan angka nonnegatif.`);
      return;
    }

    if (!hasAny) {
      setError('Isi minimal satu nilai rate.');
      return;
    }

    setError(null);
    onGenerate(payload, {
      title: boardTitle || 'MONEY CHANGER',
      subtitle: boardSubtitle || APP_COMPANY,
      logoUrl: boardLogoUrl || null,
      branchId: branchId ?? null,
    });
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          alignItems: 'flex-start',
          marginBottom: 20,
          '@media (min-width: 640px)': {
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          },
        }}
      >
        <div>
          <h2
            style={{
              fontSize: 18,
              fontWeight: 800,
              color: '#0D47A1',
              marginBottom: 4,
              '@media (min-width: 640px)': { fontSize: 20 },
            }}
          >
            Edit Extracted Rates
          </h2>
          <p style={{ fontSize: 13, color: '#607D8B' }}>Review and correct the OCR results. All fields are editable.</p>
        </div>
        <div
          style={{
            background: '#E3F2FD',
            borderRadius: 10,
            padding: '8px 16px',
            textAlign: 'center',
            minWidth: '140px',
            flexShrink: 0,
          }}
        >
          <div style={{ fontSize: 10, color: '#1565C0', fontWeight: 600 }}>DETECTED</div>
          <div style={{ fontSize: 22, fontWeight: 900, color: '#0D47A1' }}>{ALL_CURRENCIES.filter((c) => values[c]).length}</div>
          <div style={{ fontSize: 10, color: '#1565C0' }}>currencies</div>
        </div>
      </div>

      {/* ── Board Customization ────────────────────────────────────────────── */}
      <div className="customization-panel animate-fade-in-up">
        <div style={{ fontSize: 13, fontWeight: 800, color: '#1565C0', marginBottom: 12, letterSpacing: 0.5 }}>
          BOARD CUSTOMIZATION
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
          {/* Title */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#607D8B', display: 'block', marginBottom: 4 }}>
              BOARD TITLE
            </label>
            <input
              type="text"
              value={boardTitle}
              onChange={(e) => onBoardTitleChange(e.target.value)}
              placeholder="MONEY CHANGER"
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1.5px solid #BBDEFB',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                color: '#0A1F6B',
                background: '#fff',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
          {/* Subtitle */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#607D8B', display: 'block', marginBottom: 4 }}>
              COMPANY NAME
            </label>
            <input
              type="text"
              value={boardSubtitle}
              onChange={(e) => onBoardSubtitleChange(e.target.value)}
              placeholder="PT. PRADNYANA ARTHA MANDIRI"
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1.5px solid #BBDEFB',
                borderRadius: 8,
                fontSize: 13,
                color: '#0A1F6B',
                background: '#fff',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Branch: only shown when the account actually has a choice to make */}
        {branches.length > 1 && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#607D8B', display: 'block', marginBottom: 4 }}>
              CABANG
            </label>
            <select
              value={branchId ?? ''}
              onChange={(e) => onBranchChange?.(e.target.value ? Number(e.target.value) : null)}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1.5px solid #BBDEFB',
                borderRadius: 8,
                fontSize: 13,
                color: '#0A1F6B',
                background: '#fff',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            >
              <option value="">— pilih cabang —</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Logo upload */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: '#607D8B', whiteSpace: 'nowrap' }}>LOGO</label>
          {boardLogoUrl && (
            <img src={boardLogoUrl} alt="logo preview" className="logo-preview" />
          )}
          <button
            type="button"
            onClick={() => logoInputRef.current?.click()}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              border: '1.5px solid #90CAF9',
              background: '#fff',
              color: '#1565C0',
              fontWeight: 700,
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            {boardLogoUrl ? '🔄 Change Logo' : '📷 Upload Logo'}
          </button>
          {boardLogoUrl && (
            <button
              type="button"
              onClick={() => onBoardLogoChange(null)}
              style={{
                padding: '7px 12px',
                borderRadius: 8,
                border: '1.5px solid #FFCDD2',
                background: '#fff',
                color: '#E53935',
                fontWeight: 700,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              ✕ Remove
            </button>
          )}
          <input
            ref={logoInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml"
            style={{ display: 'none' }}
            onChange={handleLogoUpload}
          />
          <span style={{ fontSize: 11, color: '#90A4AE' }}>PNG, JPG, SVG</span>
        </div>
      </div>

      {/* USD derived values */}
      <DerivedValuesBox usdValue={usdVal} usdTValue={values['USDT']} usdKValue={values['USDK']} onUsdTChange={handleChange} onUsdKChange={handleChange} />

      {/* Rate Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: 16,
          marginBottom: 20,
          '@media (min-width: 640px)': {
            gridTemplateColumns: '1fr 1fr',
            gap: 10,
          },
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: '#90A4AE',
              marginBottom: 8,
              letterSpacing: 1,
            }}
          >
            LEFT COLUMN
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {LEFT_COL.map((c) => (
              <CurrencyInput key={c} code={c} value={values[c]} onChange={handleChange} />
            ))}
          </div>
        </div>
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: '#90A4AE',
              marginBottom: 8,
              letterSpacing: 1,
            }}
          >
            RIGHT COLUMN
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {RIGHT_COL.map((c) => (
              <CurrencyInput key={c} code={c} value={values[c]} onChange={handleChange} />
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '10px 16px',
            background: '#FFEBEE',
            borderRadius: 8,
            color: '#C62828',
            fontSize: 13,
            marginBottom: 16,
            border: '1px solid #FFCDD2',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="responsive-button"
        style={{
          background: loading ? '#CFD8DC' : 'linear-gradient(135deg, #0D47A1, #1E88E5)',
          color: '#fff',
          border: 'none',
          fontWeight: 900,
          cursor: loading ? 'not-allowed' : 'pointer',
          boxShadow: loading ? 'none' : '0 6px 20px rgba(13,71,161,0.3)',
          letterSpacing: 0.5,
          transition: 'all 0.25s',
        }}
      >
        {loading ? '⏳ Membuat & Menyimpan...' : '🎨 Generate & Save'}
      </button>
    </div>
  );
}
