import { beforeEach, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import type { AssistantThreadDetail } from "../api/assistant";
import { json, mockApi, renderApp, tenant } from "./helpers";

const chatId = "00000000-0000-4000-8000-000000000001";
const reply: AssistantThreadDetail = {
  id: chatId,
  title: "Find a room",
  updated_at: "2026-10-28T10:00:00Z",
  messages: [
    {
      id: "answer",
      role: "assistant",
      content: "Your search is ready.",
      created_at: "2026-10-28T10:00:00Z",
      listings: [],
      actions: [],
    },
  ],
};

beforeEach(() => {
  localStorage.removeItem("casa:companion:v1");
  sessionStorage.clear();
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn(() => 1),
  );
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
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
    fillRect: vi.fn(),
    restore: vi.fn(),
    globalAlpha: 1,
  } as unknown as CanvasRenderingContext2D);
});

function deferredResponse() {
  let finish!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const mock = mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return response;
    if (path === `/assistant/threads/${chatId}`) return json(reply);
  });
  return { finish, ...mock };
}

async function sendPopupRequest() {
  fireEvent.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const input = await screen.findByLabelText("Message Blu");
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: "Find a room" } });
  fireEvent.click(screen.getByRole("button", { name: "Send request to Blu" }));
}

function waitForPhase(walker: Element, phase: string) {
  return waitFor(
    () => expect(walker).toHaveAttribute("data-work-phase", phase),
    { timeout: 1800 },
  );
}

it("keeps Blu working with the popup closed, then packs the laptop and stands", async () => {
  const { finish } = deferredResponse();
  const { container } = renderApp("/");
  const walker = container.querySelector(".companion-walker")!;
  await sendPopupRequest();
  expect(walker).toHaveAttribute("data-work-phase", "opening");
  expect(walker).toHaveAttribute("data-activity", "work");
  await waitForPhase(walker, "working");
  fireEvent.click(screen.getByRole("button", { name: "Close Blu" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(walker).toHaveAttribute("data-work-phase", "working");

  await act(async () => finish(json(reply)));
  await waitForPhase(walker, "packing");
  expect(walker).toHaveAttribute("data-activity", "packing");
  await waitForPhase(walker, "idle");
  expect(walker).toHaveAttribute("data-activity", "idle");
  fireEvent.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  expect(screen.getByText("Your search is ready.")).toBeInTheDocument();
});

it("finishes opening before packing even when a reply arrives immediately", async () => {
  const { finish } = deferredResponse();
  const { container } = renderApp("/");
  const walker = container.querySelector(".companion-walker")!;
  await sendPopupRequest();
  await act(async () => finish(json(reply)));
  await screen.findByText("Your search is ready.");
  expect(walker).toHaveAttribute("data-work-phase", "opening");
  await waitForPhase(walker, "packing");
  await waitForPhase(walker, "idle");
  expect(walker).toHaveAttribute("data-activity", "idle");
});

it("uses a static laptop for reduced motion and stands after a failed request", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  const { finish } = deferredResponse();
  const { container } = renderApp("/");
  const walker = container.querySelector(".companion-walker")!;
  await sendPopupRequest();
  expect(walker).toHaveAttribute("data-work-phase", "working");
  expect(walker).toHaveAttribute("data-activity", "work");
  expect(walker).toHaveAttribute("data-paused", "true");
  expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  await act(async () =>
    finish(json({ error: { message: "The search failed." } }, 503)),
  );
  await screen.findByText("The search failed.");
  await waitForPhase(walker, "idle");
  expect(walker).toHaveAttribute("data-activity", "idle");
  expect(screen.getByLabelText("Message Blu")).toHaveValue("Find a room");
});

it("works for dashboard requests and clears the laptop when navigation aborts one", async () => {
  localStorage.setItem(
    "casa:companion:v1",
    JSON.stringify({ visible: true, paused: true }),
  );
  const { fetchMock } = deferredResponse();
  const { container } = renderApp("/tenant/assistant");
  const walker = container.querySelector(".companion-walker")!;
  const input = await screen.findByLabelText("Message the assistant");
  await waitFor(() => expect(input).toBeEnabled());
  expect(walker).toHaveAttribute("data-work-phase", "idle");
  fireEvent.change(input, { target: { value: "Find a room" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(walker).toHaveAttribute("data-work-phase", "working");
  expect(walker).toHaveAttribute("data-activity", "work");
  const request = fetchMock.mock.calls.find(([url]) =>
    String(url).endsWith("/assistant/chat"),
  )?.[1];
  expect(request?.signal?.aborted).toBe(false);
  fireEvent.click(screen.getByRole("link", { name: "Explore homes" }));
  await waitFor(() => expect(request?.signal?.aborted).toBe(true));
  await waitForPhase(walker, "idle");
  expect(walker).toHaveAttribute("data-activity", "idle");
});
