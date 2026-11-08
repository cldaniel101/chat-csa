// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ModalLayer } from "./KBExplorer";

describe("ModalLayer", () => {
  let trigger: HTMLButtonElement;
  let originalGetClientRects: typeof HTMLElement.prototype.getClientRects;

  beforeEach(() => {
    trigger = document.createElement("button");
    trigger.textContent = "Abrir";
    document.body.appendChild(trigger);
    trigger.focus();

    originalGetClientRects = HTMLElement.prototype.getClientRects;
    HTMLElement.prototype.getClientRects = () => [{ width: 10, height: 10 }] as unknown as DOMRectList;
  });

  afterEach(() => {
    cleanup();
    trigger.remove();
    HTMLElement.prototype.getClientRects = originalGetClientRects;
    document.body.style.overflow = "";
  });

  it("isola o fundo, prende o foco e o devolve ao fechar", () => {
    const onClose = vi.fn();
    const rendered = render(
      <ModalLayer labelledBy="modal-title" onClose={onClose}>
        <div>
          <h2 id="modal-title">Confirmação</h2>
          <button type="button" data-modal-autofocus>Cancelar</button>
          <button type="button">Confirmar</button>
        </div>
      </ModalLayer>,
    );

    const cancel = screen.getByRole("button", { name: "Cancelar" });
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    const dialog = screen.getByRole("dialog");

    expect(document.activeElement).toBe(cancel);
    expect(document.body.style.overflow).toBe("hidden");
    expect(rendered.container.inert).toBe(true);
    expect(rendered.container.getAttribute("aria-hidden")).toBe("true");

    confirm.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(cancel);

    trigger.focus();
    expect(document.activeElement).toBe(cancel);

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();

    rendered.unmount();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
    expect(rendered.container.inert).toBeFalsy();
    expect(rendered.container.hasAttribute("aria-hidden")).toBe(false);
  });
});
