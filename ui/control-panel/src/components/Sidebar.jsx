import { useEffect, useRef, useState } from "react";

const navItems = [
    { id: "models", label: "Models", icon: "M" },
    { id: "plugins", label: "Plugins", icon: "P" },
    { id: "supervisor", label: "Supervisor", icon: "S" },
    { id: "plugin-actions", label: "Install", icon: "+" },
    { id: "logs", label: "Logs", icon: "L" },
    { id: "task-history", label: "Tasks", icon: "T" },
];

export default function Sidebar({ onNavigate, workspace = "local", onWorkspaceChange, selectedSection, setSelectedSection }) {
    const [width, setWidth] = useState(220);
    const [collapsed, setCollapsed] = useState(false);
    const [focusedIndex, setFocusedIndex] = useState(0);
    const barRef = useRef(null);

    useEffect(() => {
        if (selectedSection) {
            const idx = navItems.findIndex((n) => n.id === selectedSection);
            if (idx >= 0) setFocusedIndex(idx);
        }
    }, [selectedSection]);

    const startResize = (e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = width;

        const onMove = (ev) => {
            const nx = Math.max(64, startWidth + (ev.clientX - startX));
            setWidth(nx);
        };

        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    };

    const handleKey = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setFocusedIndex((i) => Math.min(i + 1, navItems.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setFocusedIndex((i) => Math.max(i - 1, 0));
        } else if (e.key === 'Enter') {
            const sel = navItems[focusedIndex];
            if (sel) {
                onNavigate && onNavigate(sel.id);
                setSelectedSection && setSelectedSection(sel.id);
            }
        }
    };

    const handleClick = (id, idx) => {
        onNavigate && onNavigate(id);
        setSelectedSection && setSelectedSection(id);
        setFocusedIndex(idx);
    };

    return (
        <div
            ref={barRef}
            role="navigation"
            aria-label="Activity Bar"
            tabIndex={0}
            onKeyDown={handleKey}
            className="vscode-sidebar"
            style={{ width: collapsed ? 56 : width, minWidth: collapsed ? 56 : 160 }}
        >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'space-between', marginBottom: 8 }}>
                {!collapsed && (<div className="workspace"><strong>Workspace</strong></div>)}
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {!collapsed && (
                        <select value={workspace} onChange={(e) => onWorkspaceChange && onWorkspaceChange(e.target.value)}>
                            <option value="local">Local</option>
                        </select>
                    )}
                    <button aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed((c) => !c)} style={{ marginLeft: 6 }}>{collapsed ? '»' : '«'}</button>
                </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: collapsed ? 'center' : 'stretch' }}>
                {navItems.map((it, idx) => {
                    const active = selectedSection === it.id;
                    const focused = focusedIndex === idx;
                    return (
                        <button
                            key={it.id}
                            title={it.label}
                            onClick={() => handleClick(it.id, idx)}
                            className={`vscode-sidebar-button ${active ? 'active' : ''}`}
                            aria-selected={active}
                        >
                            <span className="vscode-activitybar-icon">{it.icon}</span>
                            {!collapsed && <span style={{ fontSize: 13 }}>{it.label}</span>}
                        </button>
                    );
                })}
            </div>

            <div style={{ flex: 1 }} />

            <div style={{ height: 6, cursor: 'ns-resize', marginTop: 8 }} />

            <div
                onMouseDown={startResize}
                style={{ width: 6, cursor: 'col-resize', position: 'relative', left: collapsed ? 28 : 0, height: '100%', marginTop: 8 }}
                aria-hidden
            />
        </div>
    );
}
