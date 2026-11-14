import { cn } from "@/lib/utils";

/*
 * Branded loader: a shape that morphs through the MMS blues (Meta-MORPH-oSys), with an orbiting dot,
 * a soft pulse ring, the page name with animated dots, and a thin indeterminate bar.
 * Styles live in index.css (.mms-loader*); prefers-reduced-motion gets a still version.
 */
export function PageLoader({ label = "Loading", className, testid = "page-loader" }) {
  return (
    <div className={cn("flex min-h-[260px] w-full flex-col items-center justify-center gap-5 py-10", className)} role="status" aria-live="polite" data-testid={testid}>
      <Mark />
      <div className="flex flex-col items-center gap-2.5">
        <p className="text-[14px] font-medium text-[#4B5361]">
          {label}<span className="mms-loader-dots" aria-hidden><i>.</i><i>.</i><i>.</i></span>
        </p>
        <span className="mms-loader-bar" aria-hidden />
      </div>
    </div>
  );
}

export function FullScreenLoader() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-7 bg-canvas" role="status" aria-live="polite" data-testid="app-loader">
      <img src="/mms-logo.png" alt="MetaMorphoSys Technologies" className="mms-loader-logo h-11 w-auto object-contain" />
      <Mark size="lg" />
      <div className="flex flex-col items-center gap-2.5">
        <p className="text-[14px] font-medium text-[#4B5361]">Preparing your workspace<span className="mms-loader-dots" aria-hidden><i>.</i><i>.</i><i>.</i></span></p>
        <span className="mms-loader-bar" aria-hidden />
      </div>
    </div>
  );
}

function Mark({ size = "md" }) {
  return (
    <span className={cn("mms-loader", size === "lg" && "mms-loader-lg")} aria-hidden>
      <span className="mms-loader-ring" />
      <span className="mms-loader-shape" />
      <span className="mms-loader-orbit"><span /></span>
    </span>
  );
}
