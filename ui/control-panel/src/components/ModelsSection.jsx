import { useState } from "react";
import { useToast } from "./Toast";

export default function ModelsSection() {
    const { showToast } = useToast();
    const [selectedModel, setSelectedModel] = useState("");

    // Available TTS models for Roamin Control Panel
    const models = [
        { id: "elevenlabs", name: "ElevenLabs (Cloud)", description: "High-quality voices, requires API key" },
        { id: "openai", name: "OpenAI TTS-1", description: "Natural sounding speech, requires API key" },
        { id: "piper", name: "Piper (Local)", description: "Privacy-focused, runs offline with local models" },
        { id: "edge-tts", name: "Edge TTS", description: "Microsoft Azure free tier voices" },
    ];

    const handleModelChange = (e) => {
        const value = e.target.value;
        setSelectedModel(value);

        if (value) {
            showToast.success(
                `TTS model "${models.find((m) => m.id === value)?.name}" selected successfully`
            );
        } else {
            showToast.info("Please select a TTS model to continue");
        }
    };

    return (
        <section className="models-section" aria-labelledby="models-heading">
            <h2 id="models-heading">TTS Models</h2>
            <p className="form-description">
                Select the text-to-speech engine for ambient audio generation. Changes take effect
                immediately.
            </p>

            <div className="form-group">
                <label htmlFor="model-select" className="form-label">
                    Available Models
                    <span aria-hidden="true" className="required-asterisk" title="Required">
                        *
                    </span>
                </label>

                <select
                    id="model-select"
                    value={selectedModel}
                    onChange={handleModelChange}
                    aria-describedby="model-hint model-error"
                    aria-invalid={selectedModel === "" && selectedModel !== undefined}
                    className="form-control"
                >
                    <option value="" disabled>
                        Select a model
                    </option>
                    {models.map((m) => (
                        <option key={m.id} value={m.id}>
                            {m.name}
                        </option>
                    ))}
                </select>

                <div id="model-hint" className="hint-text">
                    Choose TTS engine for ambient audio generation. Selected model will be applied
                    automatically when you start the Roamin agent.
                </div>

                <div
                    id="model-error"
                    role="alert"
                    className="error-message error-hidden"
                    aria-live="polite"
                >
                    TTS model is required to generate audio output.
                </div>
            </div>

            <details className="model-details">
                <summary className="model-summary">How to configure your selected model</summary>

                <div className="form-group">
                    <h3>ElevenLabs Setup</h3>
                    <p>
                        1. Sign up at{" "}
                        <a href="https://elevenlabs.io" target="_blank" rel="noopener noreferrer">
                            elevenlabs.io
                        </a>
                        <br />
                        2. Get your API key from the dashboard
                        <br />
                        3. Enter it in the Plugins tab below
                    </p>
                </div>

                <div className="form-group">
                    <h3>OpenAI TTS-1 Setup</h3>
                    <p>
                        1. Visit{" "}
                        <a
                            href="https://platform.openai.com/api-keys"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            OpenAI API Keys
                        </a>
                        <br />
                        2. Create a new secret key
                        <br />
                        3. Paste it in the Plugins tab
                    </p>
                </div>

                <div className="form-group">
                    <h3>Piper (Local) Setup</h3>
                    <p>
                        1. Download Piper from the official repository
                        <br />
                        2. Place model files in the configured models directory
                        <br />
                        3. No API key required - runs entirely on your machine
                    </p>
                </div>
            </details>
        </section>
    );
}
