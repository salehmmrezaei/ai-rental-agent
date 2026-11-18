# Blu companion

Blu is the small blue robot in the corner of Casa. It opens the same role-scoped chat as the dashboard assistant, including verified listing cards. Public-demo replies are simulated.

## Interaction

Blu can walk, wave, read, listen to music, use its phone, jump and react to petting. It opens a small laptop while a request is running.

- Chat and activity controls work with keyboard input.
- Pause/hide preferences persist locally.
- Animation pauses in hidden tabs and respects reduced-motion preferences.
- Signing out removes private chat content; switching roles starts an independent view.
- A listing or managed property can provide context, with access checked by the backend.

Animations use local assets and do not call an AI service.

## Source and artwork

| File under `frontend/` | Purpose |
| --- | --- |
| `src/components/FloatingCompanion.tsx` | Rendering, controls and animation lifecycle |
| `src/components/CompanionChat.tsx` | Chat, history and current-property context |
| `src/components/AssistantMessages.tsx` | Shared listing, visit and action cards |
| `src/components/companion-motion.ts` | Movement and timing |
| `src/components/companion-laptop.ts` | Laptop overlay and transitions |
| `src/hooks/useCompanionWork.ts` | Working-state animation |
| `src/hooks/useAssistantActivity.ts` | Shared request tracking |
| `public/pets/blue-companion-cute-atlas.png` | Current transparent sprite atlas |
| `src/assets/blue-companion-cute-atlas.json` | Frame bounds and anchors |

The artwork was generated from the existing mascot reference and is bundled with the app. The current atlas contains 60 frames across ten activities; the original atlas is retained.

[Assistant behavior](assistant.md) · [Tests](development.md#tests)
