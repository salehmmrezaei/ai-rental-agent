import { useEffect, useId, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  Headphones,
  Heart,
  MessageCircle,
  Moon,
  Pause,
  Play,
  Smartphone,
  Sparkles,
  X,
} from "lucide-react";
import atlas from "../assets/blue-companion-cute-atlas.json";
import { useAssistantBusy } from "../hooks/useAssistantActivity";
import { useCompanionWork } from "../hooks/useCompanionWork";
import { CompanionChat } from "./CompanionChat";
import { drawCompanionLaptop } from "./companion-laptop";
import {
  activities,
  movePet,
  shuffledActivities,
  walkingLimit,
} from "./companion-motion";
import type { PetActivity } from "./companion-motion";
import "./FloatingCompanion.css";

const preferenceKey = "casa:companion:v1";
interface Preferences {
  visible: boolean;
  paused: boolean;
}

function readPreferences(): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(preferenceKey) || "null");
    return {
      visible: value?.visible !== false,
      paused: value?.paused === true,
    };
  } catch {
    return { visible: true, paused: false };
  }
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () =>
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

export function FloatingCompanion() {
  const [preferences, setPreferences] = useState(readPreferences);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [tab, setTab] = useState<"chat" | "activities">("chat");
  const thinking = useAssistantBusy();
  const [mode, setMode] = useState<PetActivity | "auto">("auto");
  const [active, setActive] = useState<PetActivity>("wave");
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [engaged, setEngaged] = useState(false);
  const reducedMotion = useReducedMotion();
  const work = useCompanionWork(
    thinking,
    loaded && preferences.visible && !preferences.paused && !reducedMotion,
  );
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const panelId = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  const image = useRef<HTMLImageElement | null>(null);
  const walker = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const autoButton = useRef<HTMLButtonElement>(null);
  const chatTab = useRef<HTMLButtonElement>(null);
  const activitiesTab = useRef<HTMLButtonElement>(null);
  const wasWorking = useRef(false);
  const engine = useRef({
    offset: 0,
    kind: "wave" as PetActivity,
    started: 0,
    plan: [
      "idle",
      "walk-left",
      "wink",
      "read",
      "walk-right",
      "sit",
      "listen",
      "phone",
      "jump",
    ] as PetActivity[],
  });

  useEffect(() => {
    try {
      localStorage.setItem(preferenceKey, JSON.stringify(preferences));
    } catch {
      /* Browsing still works without storage. */
    }
  }, [preferences]);

  useEffect(() => {
    const picture = new Image();
    picture.onload = () => {
      image.current = picture;
      setLoaded(true);
    };
    picture.onerror = () => setFailed(true);
    picture.src = `${import.meta.env.BASE_URL}pets/blue-companion-cute-atlas.png`;
    return () => {
      picture.onload = null;
      picture.onerror = null;
      image.current = null;
    };
  }, []);

  useEffect(() => {
    const changed = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);

  useEffect(() => {
    if (
      (work.phase === "idle" && wasWorking.current) ||
      (work.phase !== "idle" && !wasWorking.current)
    ) {
      // Finish upright, then let Blu return to its usual automatic activities.
      engine.current.kind = "idle";
      engine.current.started = performance.now();
      setActive("idle");
      setMode("auto");
    }
    wasWorking.current = work.phase !== "idle";
  }, [work.phase]);

  useEffect(() => {
    if (!open) return;
    if (tab === "activities") autoButton.current?.focus();
    else chatTab.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        toggle.current?.focus();
      }
    };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target))
        setOpen(false);
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open, tab]);

  useEffect(() => {
    if (!preferences.visible || !loaded || !canvas.current || !image.current)
      return;
    const context = canvas.current.getContext("2d");
    if (!context) return;
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.current.width = 72 * pixelRatio;
    canvas.current.height = 80 * pixelRatio;
    const state = engine.current;
    state.kind = mode === "auto" ? state.kind : mode;
    state.started = performance.now();
    state.offset = Math.min(state.offset, walkingLimit(window.innerWidth));
    let request = 0;
    let previous = state.started;
    let lastDraw = -Infinity;
    const moving = !preferences.paused && !reducedMotion && pageVisible;

    function draw(now: number) {
      if (!context || !image.current) return;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.clearRect(0, 0, 72, 80);
      context.imageSmoothingEnabled = false;
      const elapsed = Math.max(0, now - work.started.current);
      function sprite(kind: PetActivity, opacity = 1, lower = 0) {
        if (!context || !image.current || opacity <= 0) return;
        const config = activities[kind];
        const frames = atlas.rows[config.row];
        const frameIndex = moving
          ? Math.floor(Math.max(0, now - state.started) / config.frameMs) %
            frames.length
          : 0;
        const frame = frames[frameIndex];
        const breathe =
          moving && config.row !== "walk" && config.row !== "jump"
            ? Math.sin(now / 700) * 0.8
            : 0;
        context.save();
        context.globalAlpha = opacity;
        context.translate(36, 68 + lower + breathe * 0.5);
        context.scale(
          kind === "walk-right" ? -atlas.sourceScale : atlas.sourceScale,
          atlas.sourceScale,
        );
        context.drawImage(
          image.current,
          frame.x,
          frame.y,
          frame.width,
          frame.height,
          -frame.anchorX,
          -frame.anchorY,
          frame.width,
          frame.height,
        );
        context.restore();
      }

      if (work.phase === "idle") {
        sprite(state.kind);
      } else {
        const seated =
          work.phase === "opening"
            ? Math.min(1, elapsed / 220)
            : work.phase === "packing"
              ? 1 - Math.max(0, Math.min(1, (elapsed - 650) / 250))
              : 1;
        sprite("idle", 1 - seated, seated * 3);
        sprite("sit", seated);
        drawCompanionLaptop(context, work.phase, elapsed, moving);
      }
    }

    function position() {
      walker.current?.style.setProperty("--pet-travel", `${-state.offset}px`);
    }

    function tick(now: number) {
      if (
        work.phase === "idle" &&
        state.kind === "pet" &&
        now - state.started >= activities.pet.duration
      ) {
        state.kind = "idle";
        state.started = now;
        setActive("idle");
        setMode("auto");
      }
      // Selecting an activity restores focus to Blu; explicit walks should continue.
      if (!open && work.phase === "idle" && (!engaged || mode !== "auto")) {
        const next = movePet(
          state.offset,
          state.kind,
          now - previous,
          walkingLimit(window.innerWidth),
        );
        state.offset = next.offset;
        if (next.kind !== state.kind) {
          state.kind = next.kind;
          setActive(next.kind);
        }
        position();
        if (
          mode === "auto" &&
          now - state.started >= activities[state.kind].duration
        ) {
          if (!state.plan.length) state.plan = shuffledActivities();
          let nextActivity = state.plan.shift()!;
          if (nextActivity === "walk-right" && state.offset < 8)
            nextActivity = "walk-left";
          if (
            nextActivity === "walk-left" &&
            state.offset >= walkingLimit(window.innerWidth) - 8
          )
            nextActivity = "walk-right";
          state.kind = nextActivity;
          state.started = now;
          setActive(nextActivity);
        }
      }
      previous = now;
      // The position is smooth at display refresh rate; sprite redraws are capped at 24 fps.
      if (now - lastDraw >= 1000 / 24) {
        draw(now);
        lastDraw = now;
      }
      request = window.requestAnimationFrame(tick);
    }

    position();
    draw(state.started);
    if (moving) request = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(request);
  }, [
    loaded,
    mode,
    open,
    pageVisible,
    preferences.paused,
    preferences.visible,
    reducedMotion,
    engaged,
    work.phase,
    work.started,
  ]);

  function choose(activity: PetActivity | "auto") {
    if (thinking) return;
    wasWorking.current = false;
    work.dismiss();
    if (activity !== "auto") {
      engine.current.kind = activity;
      setActive(activity);
    }
    setMode(activity);
    setOpen(false);
    toggle.current?.focus();
  }

  function hide() {
    setOpen(false);
    setPreferences((current) => ({ ...current, visible: false }));
  }

  function pet() {
    if (thinking) return;
    wasWorking.current = false;
    work.dismiss();
    engine.current.kind = "pet";
    engine.current.started = performance.now();
    setActive("pet");
    setMode("pet");
  }

  function changeTab(next: "chat" | "activities") {
    setTab(next);
    (next === "chat" ? chatTab : activitiesTab).current?.focus();
  }

  if (!preferences.visible)
    return (
      <button
        className="companion-restore"
        aria-label="Show Blu companion"
        title="Bring Blu back"
        onClick={() =>
          setPreferences((current) => ({ ...current, visible: true }))
        }
      >
        <Sparkles size={18} aria-hidden="true" />
      </button>
    );

  return (
    <aside ref={root} className="companion" aria-label="Blu companion">
      {mounted && (
        <section
          id={panelId}
          className="companion-panel"
          role="dialog"
          aria-label="Blu assistant"
          hidden={!open}
        >
          <header>
            <div>
              <span className="companion-eyebrow">Your tiny rental helper</span>
              <h2>
                Blu <span aria-hidden="true">♡</span>
              </h2>
              <p className="companion-status">
                {thinking
                  ? "Working on your request…"
                  : work.phase !== "idle"
                    ? "Putting my laptop away…"
                    : "Little robot. Big helping hand."}
              </p>
            </div>
            <div className="companion-header-actions">
              <button
                className="companion-pet-button"
                aria-label="Give Blu a head pat"
                title="Pet Blu"
                disabled={thinking}
                onClick={pet}
              >
                <Heart size={17} />
              </button>
              <button
                className="companion-close"
                aria-label="Close Blu"
                onClick={() => {
                  setOpen(false);
                  toggle.current?.focus();
                }}
              >
                <X size={17} />
              </button>
            </div>
          </header>
          <div
            className="companion-tabs"
            role="tablist"
            aria-label="Blu options"
            onKeyDown={(event) => {
              if (
                ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              ) {
                event.preventDefault();
                changeTab(
                  event.key === "Home"
                    ? "chat"
                    : event.key === "End"
                      ? "activities"
                      : tab === "chat"
                        ? "activities"
                        : "chat",
                );
              }
            }}
          >
            <button
              ref={chatTab}
              role="tab"
              id={`${panelId}-chat-tab`}
              aria-selected={tab === "chat"}
              aria-controls={`${panelId}-chat`}
              tabIndex={tab === "chat" ? 0 : -1}
              onClick={() => changeTab("chat")}
            >
              <MessageCircle size={15} />
              Chat
            </button>
            <button
              ref={activitiesTab}
              role="tab"
              id={`${panelId}-activities-tab`}
              aria-selected={tab === "activities"}
              aria-controls={`${panelId}-activities`}
              tabIndex={tab === "activities" ? 0 : -1}
              onClick={() => changeTab("activities")}
            >
              <Sparkles size={15} />
              Activities
            </button>
          </div>
          <div
            id={`${panelId}-chat`}
            role="tabpanel"
            aria-labelledby={`${panelId}-chat-tab`}
            hidden={tab !== "chat"}
          >
            <CompanionChat active={open && tab === "chat"} />
          </div>
          <div
            id={`${panelId}-activities`}
            className="companion-activity-panel"
            role="tabpanel"
            aria-labelledby={`${panelId}-activities-tab`}
            hidden={tab !== "activities"}
          >
            <p>
              A tiny break? Pick something fun, or give Blu a little head pat.
            </p>
            <button
              ref={autoButton}
              className={`companion-auto ${mode === "auto" ? "selected" : ""}`}
              aria-pressed={mode === "auto"}
              disabled={thinking}
              onClick={() => choose("auto")}
            >
              <Sparkles size={17} />
              Explore & relax
              <span>{mode === "auto" ? <Check size={15} /> : "Auto"}</span>
            </button>
            <div className="companion-activities">
              {(
                Object.entries(activities) as [
                  PetActivity,
                  (typeof activities)[PetActivity],
                ][]
              ).map(([key, value]) => (
                <button
                  key={key}
                  aria-pressed={mode === key}
                  disabled={thinking}
                  className={mode === key ? "selected" : ""}
                  onClick={() => choose(key)}
                >
                  <span aria-hidden="true">
                    {key === "pet" ? (
                      <Heart size={16} />
                    ) : key === "read" ? (
                      <BookOpen size={16} />
                    ) : key === "listen" ? (
                      <Headphones size={16} />
                    ) : key === "phone" ? (
                      <Smartphone size={16} />
                    ) : key === "sit" ? (
                      <Moon size={16} />
                    ) : key === "walk-left" ? (
                      "←"
                    ) : key === "walk-right" ? (
                      "→"
                    ) : key === "wave" ? (
                      "✋"
                    ) : key === "wink" ? (
                      ";)"
                    ) : key === "jump" ? (
                      "↑"
                    ) : (
                      "•"
                    )}
                  </span>
                  {value.label}
                </button>
              ))}
            </div>
            {reducedMotion && (
              <p className="companion-motion-note">
                Motion is off to match your reduced-motion preference. You can
                still choose a pose.
              </p>
            )}
            {failed && (
              <p className="companion-motion-note">
                Blu couldn’t load. Refresh the page to try again.
              </p>
            )}
            <footer>
              <button
                disabled={reducedMotion}
                onClick={() =>
                  setPreferences((current) => ({
                    ...current,
                    paused: !current.paused,
                  }))
                }
              >
                {preferences.paused ? <Play size={15} /> : <Pause size={15} />}
                {preferences.paused ? "Resume animations" : "Pause animations"}
              </button>
              <button onClick={hide}>
                <ChevronDown size={16} />
                Hide Blu
              </button>
            </footer>
          </div>
        </section>
      )}
      <div
        ref={walker}
        className="companion-walker"
        data-activity={
          work.phase === "packing"
            ? "packing"
            : work.phase !== "idle"
              ? "work"
              : active
        }
        data-work-phase={work.phase}
        data-paused={preferences.paused || reducedMotion || !pageVisible}
      >
        <span className="companion-shadow" aria-hidden="true" />
        <button
          ref={toggle}
          className="companion-character"
          aria-label="Open Blu assistant"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          title={
            thinking
              ? "Blu is working on your request…"
              : work.phase !== "idle"
                ? "Blu is putting its laptop away…"
                : `Blu is ${activities[active].description}. Click to chat.`
          }
          onPointerEnter={() => setEngaged(true)}
          onPointerLeave={() => setEngaged(false)}
          onFocus={() => setEngaged(true)}
          onBlur={() => setEngaged(false)}
          onClick={() => {
            setMounted(true);
            setTab("chat");
            setOpen((current) => !current);
          }}
        >
          <canvas ref={canvas} aria-hidden="true" width={72} height={80} />
          {!loaded && (
            <span className="companion-loading" aria-hidden="true">
              <Sparkles size={20} />
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
