import { beforeEach, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../auth/AuthProvider";
import { mockApi } from "./helpers";
import { FloatingCompanion } from "../components/FloatingCompanion";
import { movePet, walkingLimit } from "../components/companion-motion";

beforeEach(() => {
  localStorage.removeItem("casa:companion:v1");
  mockApi();
});
function renderPet() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <FloatingCompanion />
      </AuthProvider>
    </MemoryRouter>,
  );
}

it("selects an activity and closes controls with keyboard focus restored", async () => {
  const { container } = renderPet();
  const user = userEvent.setup();
  const toggle = screen.getByRole("button", { name: "Open Blu assistant" });
  await user.click(toggle);
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  expect(
    screen.getByRole("dialog", { name: "Blu assistant" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Read a book" }));
  expect(container.querySelector(".companion-walker")).toHaveAttribute(
    "data-activity",
    "read",
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(toggle).toHaveFocus();
  await user.click(toggle);
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(toggle).toHaveFocus();
});

it("moves in both selected walking directions while launcher focus is restored", async () => {
  let now = 0;
  let nextFrame = 0;
  const frames = new Map<number, FrameRequestCallback>();
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++nextFrame, callback);
    return nextFrame;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    save: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    drawImage: vi.fn(),
    restore: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  function advanceFrames(count: number) {
    act(() => {
      for (let index = 0; index < count; index++) {
        now += 16;
        const callbacks = [...frames.values()];
        frames.clear();
        callbacks.forEach((callback) => callback(now));
      }
    });
  }
  const { container } = renderPet();
  const user = userEvent.setup();
  const toggle = screen.getByRole("button", { name: "Open Blu assistant" });
  const walker = container.querySelector<HTMLElement>(".companion-walker")!;
  const travel = () =>
    parseFloat(walker.style.getPropertyValue("--pet-travel"));
  await waitFor(() => expect(frames.size).toBe(1));
  await user.click(toggle);
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  await user.click(screen.getByRole("button", { name: "Walk left" }));
  expect(toggle).toHaveFocus();
  const initial = travel();
  advanceFrames(40);
  const left = travel();
  expect(left).toBeLessThan(initial - 1);
  expect(walker).toHaveAttribute("data-activity", "walk-left");
  expect(toggle).toHaveFocus();

  await user.click(toggle);
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  await user.click(screen.getByRole("button", { name: "Walk right" }));
  advanceFrames(20);
  expect(travel()).toBeGreaterThan(left + 1);
  expect(walker).toHaveAttribute("data-activity", "walk-right");
  expect(toggle).toHaveFocus();

  await user.click(toggle);
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  await user.click(screen.getByRole("button", { name: "Pause animations" }));
  await user.keyboard("{Escape}");
  const paused = travel();
  advanceFrames(20);
  expect(travel()).toBe(paused);
  expect(walker).toHaveAttribute("data-paused", "true");
});

it("persists pause and hide preferences and allows restoring the companion", async () => {
  const { container, unmount } = renderPet();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  await user.click(screen.getByRole("button", { name: "Pause animations" }));
  expect(container.querySelector(".companion-walker")).toHaveAttribute(
    "data-paused",
    "true",
  );
  await user.click(screen.getByRole("button", { name: "Hide Blu" }));
  expect(
    screen.queryByRole("button", { name: "Open Blu assistant" }),
  ).not.toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("casa:companion:v1")!)).toEqual({
    visible: false,
    paused: true,
  });
  unmount();
  renderPet();
  await user.click(screen.getByRole("button", { name: "Show Blu companion" }));
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  await user.click(screen.getByRole("tab", { name: "Activities" }));
  expect(
    screen.getByRole("button", { name: "Resume animations" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Resume animations" }));
  expect(JSON.parse(localStorage.getItem("casa:companion:v1")!).paused).toBe(
    false,
  );
  localStorage.removeItem("casa:companion:v1");
});

it("respects reduced motion while allowing static activity choices", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  const { container } = renderPet();
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await userEvent.click(screen.getByRole("tab", { name: "Activities" }));
  expect(container.querySelector(".companion-walker")).toHaveAttribute(
    "data-paused",
    "true",
  );
  expect(
    screen.getByRole("button", { name: "Pause animations" }),
  ).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Headphones" }));
  expect(container.querySelector(".companion-walker")).toHaveAttribute(
    "data-activity",
    "listen",
  );
});

it("keeps walking within mobile and desktop bounds and reverses at each edge", () => {
  for (const width of [320, 390, 768, 1440]) {
    const limit = walkingLimit(width);
    expect(limit).toBeLessThanOrEqual(width - 164);
    expect(movePet(limit - 0.1, "walk-left", 1000, limit)).toEqual({
      offset: limit,
      kind: "walk-right",
    });
    expect(movePet(0.1, "walk-right", 1000, limit)).toEqual({
      offset: 0,
      kind: "walk-left",
    });
  }
  expect(movePet(20, "walk-left", -5, 100)).toEqual({
    offset: 20,
    kind: "walk-left",
  });
});
