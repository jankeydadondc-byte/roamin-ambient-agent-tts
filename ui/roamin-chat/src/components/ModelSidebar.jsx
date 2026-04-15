import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  getCurrentModel,
  getSystemPrompt,
  getModelParams,
  setModelParams,
  getSystemSpecs,
  estimateModel,
} from "../apiClient";

const KV_QUANT_OPTIONS = ["f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1"];

const GUARDRAIL_VERDICT_STYLE = {
  ok:    { color: "#4caf50", icon: "✓" },
  warn:  { color: "#f9a825", icon: "⚠" },
  block: { color: "#e06c75", icon: "✗" },
};

const PARAM_DEFAULTS = {
  temperature: 0.7, top_p: 0.95, top_k: 40, repeat_penalty: 1.1,
  max_tokens: 2048, context_length: 8192,
  n_gpu_layers: -1, n_threads: -1, n_batch: 512, n_parallel: 1,
  use_mlock: false, use_mmap: true, flash_attn: true, offload_kv: true,
  rope_freq_base: 0.0, rope_freq_scale: 0.0,
  type_k: "f16", type_v: "f16", seed: -1,
};

/**
 * Right-overlay panel: active model info, LM Studio-parity parameters,
 * live memory estimate bar, and system prompt display.
 */
export default function ModelSidebar({ onClose, selectedModel, models = [] }) {
  const [routingData, setRoutingData]     = useState(null);
  const [promptData, setPromptData]       = useState(null);
  const [promptExpanded, setPromptExpanded]   = useState(false);
  const [sidecarExpanded, setSidecarExpanded] = useState(false);
  const [specs, setSpecs]                 = useState(null);   // system hardware
  const [estimate, setEstimate]           = useState(null);   // memory estimate
  const [params, setParams]               = useState(PARAM_DEFAULTS);
  const [guardrailTier, setGuardrailTier] = useState("balanced");
  const [saving, setSaving]               = useState(false);
  const [saved, setSaved]                 = useState(false);
  const estimateTimer = useRef(null);

  // Load everything on mount
  useEffect(() => {
    getCurrentModel().then(setRoutingData).catch(() => {});
    getSystemPrompt().then(setPromptData).catch(() => {});
    getSystemSpecs().then(setSpecs).catch(() => {});
    getModelParams().then((d) => {
      if (d?.params) setParams((p) => ({ ...PARAM_DEFAULTS, ...d.params }));
      if (d?.guardrail_tier) setGuardrailTier(d.guardrail_tier);
    }).catch(() => {});
  }, []);

  // Re-estimate whenever params or selectedModel change (debounced 400ms)
  const triggerEstimate = useCallback(() => {
    if (!selectedModel) { setEstimate(null); return; }
    if (estimateTimer.current) clearTimeout(estimateTimer.current);
    estimateTimer.current = setTimeout(async () => {
      try {
        const est = await estimateModel(selectedModel, params);
        setEstimate(est);
      } catch (_) {}
    }, 400);
  }, [selectedModel, params]);

  useEffect(() => { triggerEstimate(); }, [triggerEstimate]);

  const activeEntry = models.find((m) => (m.id || m) === selectedModel) || null;
  const modelName   = activeEntry?.name || selectedModel || "Auto (config default)";
  const overrides   = routingData?.overrides || {};
  const prompts     = promptData?.prompts || {};
  const vram        = specs?.gpus?.[0]?.vram_total_gb ?? 0;
  const vramFree    = specs?.gpus?.[0]?.vram_free_gb ?? 0;
  const gpuName     = specs?.gpus?.[0]?.name ?? "No GPU";

  const statusColors = { loaded: "#4caf50", available: "var(--accent)", unavailable: "var(--text-secondary)" };

  const handleParam = (key, val) => {
    setParams((p) => ({ ...p, [key]: val }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    await setModelParams({ ...params, guardrail_tier: guardrailTier }).catch(() => {});
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => { setParams(PARAM_DEFAULTS); setSaved(false); };

  // Memory estimate bar fill %
  const usedGb   = estimate?.total_vram_gb ?? 0;
  const barPct   = vram > 0 ? Math.min(100, (usedGb / vram) * 100) : 0;
  const verdict  = estimate?.guardrail_verdict ?? "ok";
  const vs       = GUARDRAIL_VERDICT_STYLE[verdict];

  const cpuCores = specs?.cpu_cores_physical ?? "?";
  const maxCtx   = estimate?.meta?.["llm.block_count"]
    ? Math.min(262144, (estimate.meta["llm.embedding_length"] ?? 4096) * 32)
    : 262144;

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay right" style={{ width: 310, overflowY: "auto" }}>
        <div className="sidebar-header">
          <span>Model Info</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="sidebar-body" style={{ padding: 0 }}>

          {/* ── Active model ── */}
          <div style={{ padding: "10px 12px 4px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-word" }}>
              {modelName}
            </div>
            {activeEntry?.provider && (
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                {activeEntry.provider}
                {activeEntry.status && (
                  <span style={{ marginLeft: 6, color: statusColors[activeEntry.status] || "inherit" }}>
                    ● {activeEntry.status}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* ── Memory estimate bar (LM Studio style) ── */}
          {estimate && (
            <div style={{ padding: "6px 12px 8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 4 }}>
                <span style={{ color: "var(--text-secondary)" }}>
                  Estimated Memory
                  <span style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: 4 }}>Beta</span>
                </span>
                <span style={{ color: vs.color, fontWeight: 600 }}>
                  {vs.icon} GPU {usedGb.toFixed(1)} GB / {vram.toFixed(1)} GB
                </span>
              </div>
              <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 3, transition: "width 0.3s",
                  width: `${barPct}%`,
                  background: verdict === "block" ? "#e06c75" : verdict === "warn" ? "#f9a825" : "var(--accent)",
                }} />
              </div>
              {estimate.reason && (
                <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 3 }}>{estimate.reason}</div>
              )}
              {vram > 0 && (
                <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>
                  {gpuName} · {vramFree.toFixed(1)} GB free
                </div>
              )}
            </div>
          )}

          <div style={{ height: 1, background: "var(--border)" }} />

          {/* ── Parameters ── */}
          <div style={{ padding: "8px 12px 4px" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>Parameters</div>

            {/* Context Length */}
            <ParamSlider label="Context Length" value={params.context_length}
              min={512} max={maxCtx} step={512}
              onChange={(v) => handleParam("context_length", v)}
              hint={`Model supports up to ${maxCtx.toLocaleString()} tokens`} />

            {/* GPU Offload */}
            <ParamSlider label="GPU Offload (layers)" value={params.n_gpu_layers < 0 ? 999 : params.n_gpu_layers}
              min={0} max={999} step={1}
              displayValue={params.n_gpu_layers < 0 ? "All" : String(params.n_gpu_layers)}
              onChange={(v) => handleParam("n_gpu_layers", v >= 999 ? -1 : v)} />

            {/* CPU Threads */}
            <ParamSlider label="CPU Thread Pool Size" value={params.n_threads < 0 ? cpuCores : params.n_threads}
              min={1} max={specs?.cpu_cores_logical ?? 32} step={1}
              displayValue={params.n_threads < 0 ? "Auto" : String(params.n_threads)}
              onChange={(v) => handleParam("n_threads", v)} />

            {/* Evaluation Batch Size */}
            <ParamSlider label="Evaluation Batch Size" value={params.n_batch}
              min={64} max={2048} step={64}
              onChange={(v) => handleParam("n_batch", v)} />

            {/* Max Concurrent Predictions */}
            <ParamSlider label="Max Concurrent Predictions" value={params.n_parallel}
              min={1} max={8} step={1}
              onChange={(v) => handleParam("n_parallel", v)} />

            {/* Sampling — temperature, top_p, top_k, repeat_penalty */}
            <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Sampling</div>

            <ParamSlider label="Temperature" value={params.temperature}
              min={0} max={2} step={0.05}
              onChange={(v) => handleParam("temperature", v)} />
            <ParamSlider label="Top P" value={params.top_p}
              min={0} max={1} step={0.01}
              onChange={(v) => handleParam("top_p", v)} />
            <ParamSlider label="Top K" value={params.top_k}
              min={1} max={200} step={1}
              onChange={(v) => handleParam("top_k", v)} />
            <ParamSlider label="Repeat Penalty" value={params.repeat_penalty}
              min={0.8} max={1.5} step={0.01}
              onChange={(v) => handleParam("repeat_penalty", v)} />

            {/* Max Tokens (number input) */}
            <div className="model-param-row">
              <div className="model-param-label"><span>Max Tokens</span></div>
              <input type="number" min={64} max={32768} step={64}
                value={params.max_tokens}
                onChange={(e) => handleParam("max_tokens", parseInt(e.target.value, 10) || 2048)}
                className="model-param-number-input" />
            </div>

            {/* Seed */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Seed</span>
                <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                  {params.seed < 0 ? "Random" : params.seed}
                </span>
              </div>
              <input type="number" min={-1} max={2147483647}
                value={params.seed}
                onChange={(e) => handleParam("seed", parseInt(e.target.value, 10))}
                className="model-param-number-input" />
            </div>

            {/* Toggles */}
            <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
            <ParamToggle label="Flash Attention" value={params.flash_attn} onChange={(v) => handleParam("flash_attn", v)} />
            <ParamToggle label="Offload KV Cache to GPU" value={params.offload_kv} onChange={(v) => handleParam("offload_kv", v)} />
            <ParamToggle label="Keep Model in Memory" value={params.use_mlock} onChange={(v) => handleParam("use_mlock", v)} />
            <ParamToggle label="Try mmap()" value={params.use_mmap} onChange={(v) => handleParam("use_mmap", v)} />

            {/* RoPE */}
            <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>RoPE</div>
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Frequency Base</span>
                <span>{params.rope_freq_base <= 0 ? "Auto" : params.rope_freq_base}</span>
              </div>
              <input type="number" min={0} max={1000000} step={100}
                value={params.rope_freq_base}
                onChange={(e) => handleParam("rope_freq_base", parseFloat(e.target.value) || 0)}
                className="model-param-number-input" />
            </div>
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Frequency Scale</span>
                <span>{params.rope_freq_scale <= 0 ? "Auto" : params.rope_freq_scale}</span>
              </div>
              <input type="number" min={0} max={4} step={0.01}
                value={params.rope_freq_scale}
                onChange={(e) => handleParam("rope_freq_scale", parseFloat(e.target.value) || 0)}
                className="model-param-number-input" />
            </div>

            {/* KV Cache types */}
            <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>KV Cache Quantization</div>
            <ParamSelect label="K Cache Type" value={params.type_k} options={KV_QUANT_OPTIONS}
              onChange={(v) => handleParam("type_k", v)} />
            <ParamSelect label="V Cache Type" value={params.type_v} options={KV_QUANT_OPTIONS}
              onChange={(v) => handleParam("type_v", v)} />

            {/* Guardrail tier */}
            <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
            <ParamSelect label="Model Load Guardrails" value={guardrailTier}
              options={["off", "relaxed", "balanced", "strict"]}
              onChange={(v) => { setGuardrailTier(v); setSaved(false); }} />

            {/* Save / Reset */}
            <div style={{ display: "flex", gap: 6, marginTop: 10, marginBottom: 4 }}>
              <button className="popover-save-btn" style={{ flex: 1 }}
                onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : saved ? "✓ Saved" : "Save"}
              </button>
              <button className="popover-save-btn"
                style={{ flex: 0, background: "rgba(224,108,117,0.15)", color: "#e06c75" }}
                onClick={handleReset}>
                Reset
              </button>
            </div>
          </div>

          <div style={{ height: 1, background: "var(--border)" }} />

          {/* ── Routing ── */}
          <div style={{ padding: "6px 12px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>Routing</div>
            {Object.keys(overrides).length > 0 ? (
              Object.entries(overrides).map(([task, mid]) => (
                <div key={task} style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  <span style={{ color: "var(--accent)" }}>{task}</span>: {mid}
                </div>
              ))
            ) : (
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Config defaults</div>
            )}
          </div>

          <div style={{ height: 1, background: "var(--border)" }} />

          {/* ── System Prompts ── */}
          <div style={{ padding: "4px 12px" }}>
            <div
              style={{ fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", padding: "4px 0", userSelect: "none" }}
              onClick={() => setPromptExpanded(!promptExpanded)}
            >
              {promptExpanded ? "▾" : "▸"} System Prompt (personality)
            </div>
            {promptExpanded && (
              <div className="model-system-prompt-block">{prompts.primary || "Not found."}</div>
            )}
            <div
              style={{ fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", padding: "4px 0", userSelect: "none" }}
              onClick={() => setSidecarExpanded(!sidecarExpanded)}
            >
              {sidecarExpanded ? "▾" : "▸"} System Prompt (sidecar)
            </div>
            {sidecarExpanded && (
              <div className="model-system-prompt-block">{prompts.sidecar || "Not found."}</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ParamSlider({ label, value, min, max, step, onChange, hint, displayValue }) {
  return (
    <div className="model-param-row">
      <div className="model-param-label">
        <span>{label}</span>
        <span>{displayValue !== undefined ? displayValue : value}</span>
      </div>
      {hint && <div style={{ fontSize: 9, color: "var(--text-secondary)", marginBottom: 2 }}>{hint}</div>}
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => {
          const v = step % 1 === 0 ? parseInt(e.target.value, 10) : parseFloat(e.target.value);
          onChange(v);
        }}
        style={{ accentColor: "var(--accent)", width: "100%" }} />
    </div>
  );
}

function ParamToggle({ label, value, onChange }) {
  return (
    <div className="model-param-row" style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
        <span style={{ fontSize: 12, color: "var(--text-primary)" }}>{label}</span>
        <label className="toggle-switch" style={{ transform: "scale(0.75)", transformOrigin: "right center" }}>
          <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
          <span className="slider" />
        </label>
      </div>
    </div>
  );
}

function ParamSelect({ label, value, options, onChange }) {
  return (
    <div className="model-param-row" style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", gap: 8 }}>
        <span style={{ fontSize: 12, color: "var(--text-primary)", flexShrink: 0 }}>{label}</span>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            fontSize: 11, padding: "2px 4px", borderRadius: 4,
            background: "var(--bg-secondary)", color: "var(--text-primary)",
            border: "1px solid var(--border)", flexShrink: 0,
          }}
        >
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    </div>
  );
}
