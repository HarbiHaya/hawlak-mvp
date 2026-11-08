import { act, type ReactElement } from "react";
import { createRoot, type Root } from "react-dom/client";

// Tell React we drive updates with act().
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

export interface Rendered {
  container: HTMLElement;
  rerender: (ui: ReactElement) => Promise<void>;
  unmount: () => Promise<void>;
}

export async function render(ui: ReactElement): Promise<Rendered> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  let root: Root | null = null;
  await act(async () => {
    root = createRoot(container);
    root.render(ui);
  });
  return {
    container,
    rerender: async (next) => {
      await act(async () => root?.render(next));
    },
    unmount: async () => {
      await act(async () => root?.unmount());
      container.remove();
    },
  };
}

/** Let pending promises and React updates settle. */
export async function flush(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

export async function click(element: Element | null): Promise<void> {
  if (!element) throw new Error("element not found");
  await act(async () => {
    (element as HTMLElement).click();
  });
}

/** Set an input's value the way React notices it. */
export async function typeInto(element: Element | null, value: string): Promise<void> {
  if (!element) throw new Error("element not found");
  const input = element as HTMLInputElement | HTMLTextAreaElement;
  const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  await act(async () => {
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

export function byText(container: HTMLElement, selector: string, text: string): HTMLElement | null {
  return (
    Array.from(container.querySelectorAll<HTMLElement>(selector)).find((el) => el.textContent?.includes(text)) ?? null
  );
}
