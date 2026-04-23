import React, { useState, useCallback } from "react";
import { setVolume } from "../apiClient";

export default function VolumeControl() {
  const [volume, setVolumeState] = useState(100);
  const [updating, setUpdating] = useState(false);

  const handleChange = useCallback(
    async (e) => {
      const val = parseInt(e.target.value, 10);
      setVolumeState(val);

      // Debounce — update backend on mouse-up or after short delay
      setUpdating(true);
      try {
        await setVolume(val / 100); // API expects 0.0-1.0
      } catch (err) {
        console.error("Volume update failed:", err);
      } finally {
        setUpdating(false);
      }
    },
    []
  );

  return (
    <div className="settings-row">
      <label>TTS Volume: {volume}%</label>
      <input
        type="range"
        min="0"
        max="100"
        value={volume}
        onChange={handleChange}
        title={`Volume: ${volume}%`}
      />
    </div>
  );
}
