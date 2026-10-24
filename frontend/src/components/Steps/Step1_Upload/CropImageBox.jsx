import { useState, useCallback } from "react";
import Cropper from "react-easy-crop";

export default function CropImageBox({ imageSrc, onCropDone, label }) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedPixels, setCroppedPixels] = useState(null);

  const onCropComplete = useCallback((_, pixels) => {
    setCroppedPixels(pixels);
  }, []);

  const createCropFile = async () => {
    const img = new Image();
    img.src = imageSrc;

    await new Promise((resolve) => {
      img.onload = resolve;
    });

    const canvas = document.createElement("canvas");
    canvas.width = croppedPixels.width;
    canvas.height = croppedPixels.height;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(
      img,
      croppedPixels.x,
      croppedPixels.y,
      croppedPixels.width,
      croppedPixels.height,
      0,
      0,
      croppedPixels.width,
      croppedPixels.height
    );

    canvas.toBlob((blob) => {
      const file = new File([blob], `${label}.png`, { type: "image/png" });
      onCropDone(file);
    }, "image/png");
  };

  return (
    <div style={{ marginBottom: 20, "@media (min-width: 640px)": { marginBottom: 24 } }}>
      <h3 style={{ fontSize: 16, marginBottom: 12, color: "#0D47A1", "@media (min-width: 640px)": { fontSize: 18 } }}>{label}</h3>

      <div style={{ position: "relative", width: "100%", height: 250, background: "#111", borderRadius: 12, overflow: "hidden", "@media (min-width: 640px)": { height: 350 } }}>
        <Cropper
          image={imageSrc}
          crop={crop}
          zoom={zoom}
          aspect={1 / 1.4}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={onCropComplete}
        />
      </div>

      <input
        type="range"
        min={1}
        max={3}
        step={0.1}
        value={zoom}
        onChange={(e) => setZoom(e.target.value)}
        style={{ width: "100%", marginTop: 12 }}
      />

      <button
        onClick={createCropFile}
        style={{
          marginTop: 12,
          width: "100%",
          padding: "10px 16px",
          background: "linear-gradient(135deg, #0D47A1, #1E88E5)",
          color: "#fff",
          border: "none",
          borderRadius: 8,
          fontWeight: 700,
          cursor: "pointer",
          fontSize: 14,
          "@media (min-width: 640px)": { fontSize: 15 }
        }}
      >
        ✓ Save {label}
      </button>
    </div>
  );
}