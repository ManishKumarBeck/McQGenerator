import { useEffect } from "react";
import { useBlocker } from "react-router";

/**
 * Warns before leaving the page while `active` is true:
 * - in-app navigation is blocked until the returned blocker is proceeded/reset,
 * - reloads and tab closes trigger the browser's native "Leave site?" prompt.
 */
export function useLeaveGuard(active: boolean) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => active && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!active) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [active]);

  // If the guard is lifted while a navigation is pending (e.g. after saving), let it through.
  useEffect(() => {
    if (blocker.state === "blocked" && !active) blocker.proceed();
  }, [active, blocker]);

  return blocker;
}
