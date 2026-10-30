import { AlertOctagon } from "lucide-react";
import { isRouteErrorResponse, useRouteError } from "react-router";
import { buttonClasses } from "../components/ui/Button";

/** Last-resort error screen for crashes while rendering a route. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";

  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="max-w-md text-center">
        <AlertOctagon className="mx-auto mb-4 size-10 text-rose-500" />
        <h1 className="text-xl font-semibold">Something broke on this page</h1>
        <p className="mt-2 text-sm text-muted">{message}</p>
        <p className="mt-1 text-sm text-muted">Any exam answers already saved are safe on the server.</p>
        <div className="mt-6 flex justify-center gap-2">
          <button className={buttonClasses("outline")} onClick={() => window.location.reload()}>
            Reload
          </button>
          <a className={buttonClasses("primary")} href="/">
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}
