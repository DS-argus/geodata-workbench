import { useEffect } from "react";
import type { RefObject } from "react";

type UseModalA11yOptions = {
  open: boolean;
  onClose?: () => void;
  modalRef: RefObject<HTMLElement | null>;
};

let modalLockCount = 0;
let lockedBodyOverflow: string | null = null;

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(", ");

function getFocusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((node) => {
    if (node.hasAttribute("disabled")) return false;
    if (node.getAttribute("aria-hidden") === "true") return false;
    return true;
  });
}

export function useModalA11y({ open, onClose, modalRef }: UseModalA11yOptions) {
  useEffect(() => {
    if (!open) {
      return;
    }

    const modal = modalRef.current;
    if (!modal) {
      return;
    }

    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (modalLockCount === 0) {
      lockedBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    modalLockCount += 1;

    const focusables = getFocusableElements(modal);
    const firstFocusable = focusables[0];
    if (firstFocusable) {
      firstFocusable.focus();
    } else {
      modal.focus();
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }

      if (event.key === "Escape" && onClose) {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const nodes = getFocusableElements(modal);
      if (!nodes.length) {
        event.preventDefault();
        modal.focus();
        return;
      }

      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (!active || active === first || !modal.contains(active)) {
          event.preventDefault();
          last.focus();
        }
        return;
      }

      if (!active || active === last || !modal.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      modalLockCount = Math.max(0, modalLockCount - 1);
      if (modalLockCount === 0) {
        document.body.style.overflow = lockedBodyOverflow ?? "";
        lockedBodyOverflow = null;
      }
      if (previousActive && document.contains(previousActive)) {
        previousActive.focus();
      }
    };
  }, [open, onClose, modalRef]);
}
