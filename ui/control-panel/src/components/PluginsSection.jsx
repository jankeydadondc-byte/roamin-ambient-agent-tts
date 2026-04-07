import { useEffect, useState } from "react";
import { useToast } from "./Toast";

// Mock API client - replace with actual apiClient calls when ready
const mockPluginAPI = {
    async getInstalledPlugins() {
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve([
                    { id: "elevenlabs", name: "ElevenLabs TTS", installed: true, version: "1.2.0" },
                    { id: "openai", name: "OpenAI TTS", installed: false, version: null },
                ]);
            }, 500);
        });
    },

    async installPlugin(pluginId) {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (pluginId === "simulated-error") {
                    reject(new Error("Installation failed: network error"));
                } else {
                    resolve({ success: true, pluginId });
                }
            }, 1000);
        });
    },
};

export default function PluginsSection() {
    const { showToast } = useToast();
    const [installedPlugins, setInstalledPlugins] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [pluginToInstall, setPluginToInstall] = useState("");
    const [isInstalling, setIsInstalling] = useState(false);

    useEffect(() => {
        loadPlugins();
    }, []);

    async function loadPlugins() {
        try {
            const plugins = await mockPluginAPI.getInstalledPlugins();
            setInstalledPlugins(plugins);
        } catch {
            showToast.error("Failed to load installed plugins. Please check your connection.");
        } finally {
            setIsLoading(false);
        }
    }

    async function handleInstall(e) {
        e.preventDefault();

        if (!pluginToInstall) {
            showToast.warning("Please select a plugin to install");
            return;
        }

        setIsInstalling(true);
        try {
            await mockPluginAPI.installPlugin(pluginToInstall);
            setInstalledPlugins((prev) =>
                prev.map((p) =>
                    p.id === pluginToInstall ? { ...p, installed: true, version: "1.0.0" } : p
                )
            );
            showToast.success(`Plugin "${pluginToInstall}" installed successfully!`);
        } catch (error) {
            showToast.error(error.message || "Installation failed");
        } finally {
            setIsInstalling(false);
        }
    }

    return (
        <section className="plugins-section" aria-labelledby="plugins-heading">
            <h2 id="plugins-heading">TTS Plugins</h2>
            <p className="form-description">
                Manage text-to-speech plugins and configure API keys. Installed plugins will appear
                in the Models tab.
            </p>

            {isLoading && (
                <div className="loading-state" role="status" aria-live="polite">
                    <div className="spinner" />
                    <span>Loading installed plugins...</span>
                </div>
            )}

            {!isLoading && installedPlugins.length > 0 && (
                <div className="plugins-list" role="list" aria-label="Installed TTS plugins">
                    {installedPlugins.map((plugin) => (
                        <article key={plugin.id} className="plugin-card" role="listitem">
                            <div className="plugin-info">
                                <h3>{plugin.name}</h3>
                                <p className="plugin-meta">
                                    Status:{" "}
                                    <span
                                        className={`status-badge ${plugin.installed ? "installed" : "not-installed"}`}
                                    >
                                        {plugin.installed ? "Installed" : "Not Installed"}
                                    </span>
                                    {plugin.version && <> &bull; Version: {plugin.version}</>}
                                </p>
                                <p className="plugin-description">
                                    {plugin.id === "elevenlabs"
                                        ? "High-quality cloud-based TTS with voice cloning support."
                                        : "Cloud-based natural sounding speech synthesis from OpenAI."}
                                </p>
                            </div>
                            {!plugin.installed && (
                                <button
                                    type="button"
                                    className="btn-secondary"
                                    aria-label={`Install ${plugin.name} plugin`}
                                >
                                    Install
                                </button>
                            )}
                        </article>
                    ))}
                </div>
            )}

            {!isLoading && installedPlugins.length === 0 && (
                <div className="empty-state" role="status" aria-live="polite">
                    <h3>No plugins detected</h3>
                    <p>Install TTS plugins below to enable audio generation.</p>
                </div>
            )}

            <form onSubmit={handleInstall} className="install-form">
                <h3>Install New Plugin</h3>

                <div className="form-group">
                    <label htmlFor="plugin-select" className="form-label">
                        Select Plugin
                        <span aria-hidden="true" className="required-asterisk" title="Required">
                            *
                        </span>
                    </label>

                    <select
                        id="plugin-select"
                        value={pluginToInstall}
                        onChange={(e) => setPluginToInstall(e.target.value)}
                        aria-describedby="install-hint install-error"
                        className="form-control"
                    >
                        <option value="" disabled>
                            Select a plugin
                        </option>
                        {installedPlugins.map((p) => (
                            <option key={p.id} value={p.id}>
                                {p.name} {p.installed ? "(already installed)" : ""}
                            </option>
                        ))}
                        <optgroup label="Available Plugins">
                            <option value="simulated-error">Simulated Error Plugin</option>
                        </optgroup>
                    </select>

                    <div id="install-hint" className="hint-text">
                        Choose a plugin to install. API keys will be configured in the next step.
                    </div>

                    <div
                        id="install-error"
                        role="alert"
                        className="error-message error-hidden"
                        aria-live="polite"
                    >
                        Please select a plugin to install
                    </div>
                </div>

                <button
                    type="submit"
                    disabled={isInstalling || !pluginToInstall}
                    className={`btn-primary ${isInstalling ? "loading" : ""}`}
                >
                    {isInstalling ? (
                        <>
                            <span className="spinner" />
                            Installing...
                        </>
                    ) : (
                        "Install Plugin"
                    )}
                </button>
            </form>

            <details className="setup-details">
                <summary className="setup-summary">How to get API keys for cloud TTS</summary>

                <div className="instructions">
                    <h4>ElevenLabs API Key</h4>
                    <ol>
                        <li>
                            Go to{" "}
                            <a
                                href="https://elevenlabs.io"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                elevenlabs.io
                            </a>
                        </li>
                        <li>Create an account or sign in</li>
                        <li>Navigate to API Keys in your account settings</li>
                        <li>Copy your API key</li>
                        <li>Paste it below when installing the plugin</li>
                    </ol>

                    <h4>OpenAI TTS-1 API Key</h4>
                    <ol>
                        <li>
                            Visit{" "}
                            <a
                                href="https://platform.openai.com/api-keys"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                OpenAI API Keys
                            </a>
                        </li>
                        <li>Create a new secret key</li>
                        <li>Select appropriate permissions for TTS access</li>
                        <li>Copy the key and use it during plugin installation</li>
                    </ol>
                </div>
            </details>
        </section>
    );
}
