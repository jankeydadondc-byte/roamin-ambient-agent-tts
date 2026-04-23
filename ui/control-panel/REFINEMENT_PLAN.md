# Roamin Control Panel - UI Refinement Plan v1.0

**Date:** 2026-04-06
**Author:** UI Expert Agent
**Status:** Ready for Implementation

---

## 🎯 Executive Summary

The Roamin Control Panel is a VS Code-styled React SPA that manages TTS plugins, monitors tasks, and displays logs. It has solid foundations but needs refinement in accessibility, error handling, and visual polish to meet WCAG 2.1 AA standards and modern UX expectations.

---

## 🔍 Current State Analysis

### Strengths
- ✅ VS Code-inspired aesthetic (familiar power user interface)
- ✅ Real-time WebSocket event stream for live updates
- ✅ Good separation of concerns in components
- ✅ Keyboard navigation in sidebar (arrow keys)
- ✅ API key management with persistence

### Areas Needing Refinement

#### 1. Accessibility Gaps (HIGH PRIORITY)
| Issue | Location | Impact | Fix |
|-------|----------|--------|-----|
| Missing `aria-live` regions | Plugin detail, logs | Screen readers won't announce updates | Add `role="status"` and `aria-live="polite"` |
| Insufficient contrast on inputs | All input fields | May fail WCAG 3:1 for UI components | Adjust border colors to ≥ 3:1 ratio |
| Focus indicator visibility | Custom buttons | Keyboard users need visible focus rings | Add high-contrast outline styles |
| Empty states lack context | Task history, plugin lists | Users confused when no data | Add helpful instructional text |
| Form errors not associated | Plugin install form | Validation messages invisible to SRs | Use `aria-describedby` for error text |

#### 2. Visual Design Improvements (MEDIUM PRIORITY)
- **Loading States**: No visual feedback for async operations
- **Error Display**: Generic browser alerts → Inline error banners
- **Color Palette**: VS Code colors but could be more modern/accessible
- **Spacing Consistency**: Some gaps between 8px, others use different values
- **Typography Hierarchy**: Section headings could have clearer scale

#### 3. UX Enhancements (MEDIUM PRIORITY)
- **Toast Notifications**: Replace alerts with custom notifications
- **Confirmation Dialogs**: Improve plugin install confirm modal
- **Search Functionality**: Add search to task history table
- **Keyboard Shortcuts**: Document and implement common shortcuts
- **Help/Onboarding**: First-time user guidance

#### 4. Code Architecture (LOW PRIORITY)
- Components could be more granular
- State lifted from App where possible
- Utility functions for validation/error handling

---

## 📋 Implementation Roadmap

### Phase 1: Critical Accessibility Fixes (Week 1)
1. Add focus indicators to all interactive elements
2. Implement `aria-live` regions for dynamic content
3. Fix color contrast on inputs and buttons
4. Associate error messages with form fields
5. Test with screen readers (NVDA/VoiceOver)

### Phase 2: UX Refinement (Week 2)
1. Create custom toast notification component
2. Implement loading skeletons for async operations
3. Replace alerts with inline error states
4. Add keyboard shortcut documentation
5. Improve empty state messages

### Phase 3: Visual Polish (Week 3)
1. Modernize color palette (darker sidebar, lighter content)
2. Consistent spacing system (8px grid)
3. Typography scale for headings
4. Refined button styles with focus states
5. Smooth transitions for hover/active states

### Phase 4: Feature Additions (Week 4+)
1. Search/filter functionality for task history
2. Modal for plugin installation confirmation
3. Onboarding tour for new users
4. Settings panel for theme/color preference

---

## 🎨 Proposed Design System Updates

### Color Palette (WCAG AA Compliant)
```css
:root {
    /* Primary Backgrounds */
    --background-primary: #1e1e1e;        /* Main app background */
    --background-secondary: #252526;       /* Sidebar, panels */
    --background-hover: #2a2d2e;           /* Hover state */

    /* Text Colors */
    --text-primary: #cccccc;               /* Primary text */
    --text-secondary: #9d9d9d;             /* Secondary/muted text */
    --text-inverse: #ffffff;               /* Text on dark backgrounds */

    /* Semantic Colors */
    --accent-color: #007acc;               /* Primary actions, links */
    --success-color: #36943b;              /* Success states */
    --error-color: #f14c4c;                /* Errors */
    --warning-color: #d89614;              /* Warnings */

    /* Borders & Separators */
    --border-primary: #3a3a3a;             /* Light borders */
    --border-secondary: #2c2c2c;           /* Dark borders */

    /* Focus Indicators (WCAG 3:1 minimum) */
    --focus-ring-color: rgba(0, 122, 204, 0.8);
    --focus-ring-width: 3px;
}
```

### Spacing System (8px Grid)
```css
--space-1: 4px;   /* Tight */
--space-2: 8px;   /* Default padding/gap */
--space-3: 12px;  /* Section padding */
--space-4: 16px;  /* Component padding */
--space-5: 24px;  /* Major sections */
```

---

## 📁 File Structure Changes

### New Files to Create
```
src/
├── main.jsx
├── App.jsx
├── apiClient.js
├── styles.css
├── components/
│   ├── Header.jsx
│   ├── Sidebar.jsx
│   ├── ModelsSection.jsx (new - refactored)
│   ├── PluginsSection.jsx (new - refactored)
│   ├── Supervisor.jsx
│   ├── TaskHistory.jsx
│   ├── LogsPanel.jsx (refactored)
│   └── PluginDetail.jsx
├── hooks/
│   ├── useWebSocket.js (extract WebSocket logic)
│   ├── useLocalStorage.js (generalized hook)
│   └── useApiStatus.js
├── utils/
│   ├── toast.js (custom notifications)
│   ├── validators.js (form validation)
│   └── focusTrap.js (modal focus management)
```

### Files to Refactor
- `App.jsx` - Lift common components out, reduce size from 8533→~4000 bytes
- `styles.css` - Add design tokens, modernize variables
- All component files - Add ARIA attributes, improve semantics

---

## ✅ Success Metrics

After refinement, the control panel should:
- [ ] Pass WCAG 2.1 AA accessibility audit (Lighthouse ≥ 90)
- [ ] Support full keyboard navigation (Tab, Enter, Escape, Arrows)
- [ ] Announce dynamic content to screen readers correctly
- [ ] Display at least 3 loading states with clear context
- [ ] Show all async operations with visual feedback
- [ ] Handle all error cases gracefully without browser alerts

---

## 🚀 Next Steps

1. **Review this plan** - Confirm priority alignment
2. **Phase 1 kickoff** - Start accessibility fixes
3. **Testing schedule** - Weekly accessibility reviews
4. **Documentation** - Update README with new keyboard shortcuts

---

**Questions?**
- How conservative should we be with the VS Code aesthetic?
- Should we add a light mode toggle?
- What's the priority: pure accessibility or feature additions first?
