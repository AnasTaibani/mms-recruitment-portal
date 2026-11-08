import * as React from "react"

import { cn } from "@/lib/utils"

const Textarea = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[60px] w-full rounded-[8px] border border-[#DCE1E7] bg-white text-ink shadow-none transition-colors hover:border-[#C9D1DB] focus-visible:outline-none focus-visible:border-brand-royal focus-visible:ring-2 focus-visible:ring-brand-royal/20 px-3 py-2 text-[14px] placeholder:text-[#9AA2AE] disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Textarea.displayName = "Textarea"

export { Textarea }
