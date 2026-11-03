# Blu — the website companion

Blu is a very small, cute blue pixel-art robot at the bottom-right of every page,
rendered about 40 pixels tall. It stands and blinks, walks left/right, waves,
winks, sits, reads a book, wears headphones, uses its phone and jumps. **Pet Blu**
adds a little head-pat reaction, rosy cheeks and hearts, then returns to automatic
mode. The heart button in the popup also pets Blu.

Click Blu to open **Chat**. Signed-in tenants, landlords and agency admins can give requests directly
from any page, see live listing cards and review/confirm proposed actions inside
the popup. They do not need to visit the dashboard assistant. Small round Chat and
Activities icon buttons sit beside the heart in the header, leaving the remaining
window height for the conversation. **Activities** keeps
all animation choices, pause/resume and hide controls. The sparkle button restores
a hidden pet. Pause/hide preferences persist in browser storage.

Chat uses the existing role-scoped `/assistant` API and the same listing/action
card components as the full dashboard assistant. Each mutation still requires an
explicit confirmation click. Visitors see a sign-in link. Landlords receive
[owner-scoped tools](landlord-assistant.md); agency admins receive
[agency tools](agency-assistant.md). API
keys stay on the backend.

The selected chat ID is stored per user in session storage; text/drafts stay in
component memory and persisted server history. Closing/reopening the popup keeps
the current conversation and draft. Signing out unmounts private chat content and
aborts its pending client request. Switching accounts creates an independent chat
view. Recent server chats can be selected from the popup; New chat clears its
selection. While viewing a published home's detail, the request includes that
listing's identifier so phrases like “this room” have context.

Blu stops wandering while hovered, keyboard-focused or its controls are open.
Animation pauses in a hidden tab and respects `prefers-reduced-motion`; with
reduced motion, activity selection changes static poses. A single animation loop
caps drawing at 24 fps and cancels callbacks on unmount, pause or hide. While
handling a request in either the popup or dashboard assistant, Blu sits down,
opens a tiny laptop and types until the request finishes. It then closes and
puts away the laptop and stands before returning to automatic activities.
Closing the popup keeps the work animation running; errors and aborted requests
also end the work sequence. Pause and reduced motion show a static working pose
and return directly to standing. Activities themselves make no AI requests; the
user must send a chat request to invoke the agent.

## Source and assets

- `frontend/src/components/FloatingCompanion.tsx`: rendering, controls, preferences and animation lifecycle.
- `frontend/src/components/companion-motion.ts`: timing and walking bounds.
- `frontend/src/components/companion-laptop.ts`: pixel-art laptop, typing hands and opening/put-away transitions drawn over the existing sprites.
- `frontend/src/hooks/useCompanionWork.ts`: sitting, working, packing and standing lifecycle, including fast replies and motion preferences.
- `frontend/src/hooks/useAssistantActivity.ts`: shared in-flight request tracking for popup and dashboard requests, confirmations and cancellations.
- `frontend/src/components/FloatingCompanion.css`: fixed placement and responsive controls.
- `frontend/public/pets/blue-companion-cute-atlas.png`: current generated RGBA atlas, 971 × 1619, ten animation rows and six frames per row. The original atlas remains preserved.
- `frontend/src/assets/blue-companion-cute-atlas.json`: actual sprite bounds and anchors, preserving consistent placement without changing the image.
- `frontend/src/components/CompanionChat.tsx`: tenant/landlord/agency chat, recent conversations, property context, request/confirmation lifecycle and role gates.
- `frontend/src/components/AssistantMessages.tsx`: shared verified listing and action cards for the popup and full assistant page.

The PNG was created with the **built-in imagegen tool**, using the user's attached
blue mascot as the visual reference and `transparent_background=true`. It is
saved in the project and does not rely on the generator's cache at runtime.
Left-facing walking frames are mirrored at render time for right-facing walking.

The current cute revision and petting row use the exact prompt in [Cute Blu artwork](companion-cute-prompt.md). The original generation prompt is preserved below.

## Original generation prompt

```text
Use case: stylized-concept. Asset type: production pixel-art character animation sprite atlas for a small website companion. Reference image: the user's attached tiny blue mascot is the character identity and exact pixel-art style reference. Generate ONE transparent-background PNG sprite sheet, portrait aspect ratio 2:3, ideally 1024x1536 pixels. EXACT layout: 6 equal square columns and 9 equal square rows, no spacing, no grid lines, no labels, no text. Each of the 54 cells contains only ONE full-body mascot frame centered horizontally, with sufficient transparent margin on every side. Identical character proportions, size, dark navy outlines and pixel size in ALL cells. The mascot is a cute cornflower-blue little robot with a fluffy scalloped blue cloud-shaped head/hood, dark blue rounded rectangular face screen, two light cyan eyes, a tiny smile, short blue arms and legs, small blue torso with pale cyan details, exactly like the reference. Low-resolution clean pixel art (designed on a 48x48 virtual pixel grid per character), visible sharp pixel steps, limited blue palette, no smooth vector outlines, no soft blurry rendering. Keep the character's head roughly 50% of the sprite height, miniature torso and small limbs. Character full height roughly 65% of each cell; feet baseline 82% down the cell, unchanged except sitting and jumping. Rows TOP TO BOTTOM, each row SIX consecutive animation frames LEFT TO RIGHT: Row 1 IDLE: standing front facing, gentle breathing, soft eye blink then eyes open; seamless loop. Row 2 WALK: same mascot walking LEFT, coherent six-frame alternating leg steps with arms swinging, body slight bob, face three-quarter left; no travel across cell. Right-walking is created in code by mirroring this row. Row 3 WAVE: front facing, raise one small hand, wave back and forth at head height, lower slightly. Row 4 WINK: front facing, one cyan eye open and other closes into a curved wink, playful smile, subtle head tilt then return. Row 5 SIT: sits down with legs forwards, rests happily, legs visibly tucked in sitting position throughout row, slight breathing/blink. Row 6 READ: sitting with a small open cream-colored book with blue cover in both hands, eyes look down, one page turning then return. Row 7 LISTEN: standing or relaxed slight crouch, wearing purple over-ear headphones with a distinct headband, gentle rhythmic nod/sway, tiny music note beside head on alternate frames, maintains headphones across frames. Row 8 PHONE: sitting, holds a tiny dark rectangular smartphone with illuminated pale cyan screen, looks down and taps phone, slight alternating hand movement, phone clearly visible. Row 9 JUMP: anticipation crouch, push-off, airborne up, airborne apex, descend, landing; preserve character identity with natural squash and stretch. Each row must remain exactly its specified activity. Props only in their assigned rows. Entire sheet has REAL alpha transparency, including between characters. No background color, no drop shadows baked into sheet, no floor, no borders, no extra characters. Precision of six columns and nine rows and consistent sizing is crucial for CSS steps animation. Never merge cells.
```

## Verification

Run `npm run build` and `npm test` from `frontend`. Interaction tests cover
activity selection, petting, keyboard dismissal/focus, pause/hide persistence,
reduced motion, walking bounds, direct chat orders without navigation, explicit
confirmation, saved conversation restoration, current-home context, failed drafts,
role gates and removing private messages on sign-out.

Local Chrome checks the tiny sprite, petting reaction, desktop/mobile popup
layout and automated accessibility. Live acceptance uses the synthetic tenant to
search for homes and prepare an agency message; the test proposal is dismissed
rather than sent. Both real model requests returned HTTP 200, six verified homes
were displayed, and the restored chat remained available after a mobile reload.
Desktop/mobile accessibility checks had no violations, no horizontal mobile
overflow occurred and no browser runtime errors were reported.

The production build and all **70 frontend tests** passed for the laptop-work revision.
