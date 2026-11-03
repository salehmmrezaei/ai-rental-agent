import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  beginAssistantRequest,
  useAssistantBusy,
} from "../hooks/useAssistantActivity";

it("keeps Blu busy until requests from both assistant surfaces finish", () => {
  const companion = new AbortController();
  const assistant = new AbortController();
  const { result } = renderHook(useAssistantBusy);
  expect(result.current).toBe(false);

  let finishCompanion!: () => void;
  let finishAssistant!: () => void;
  act(() => {
    finishCompanion = beginAssistantRequest(companion.signal);
    finishAssistant = beginAssistantRequest(assistant.signal);
  });
  expect(result.current).toBe(true);

  act(() => finishCompanion());
  expect(result.current).toBe(true);
  act(() => finishAssistant());
  expect(result.current).toBe(false);
});

it("clears an aborted request immediately and safely ignores its later completion", () => {
  const controller = new AbortController();
  const finish = beginAssistantRequest(controller.signal);
  const { result } = renderHook(useAssistantBusy);
  expect(result.current).toBe(true);

  act(() => controller.abort());
  expect(result.current).toBe(false);

  const next = new AbortController();
  let finishNext!: () => void;
  act(() => {
    finishNext = beginAssistantRequest(next.signal);
    finish();
    beginAssistantRequest(controller.signal)();
  });
  expect(result.current).toBe(true);
  act(() => finishNext());
  expect(result.current).toBe(false);
});
