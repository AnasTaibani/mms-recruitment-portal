import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-[8px] border border-[#DCE1E7] bg-white text-ink shadow-none transition-colors hover:border-[#C9D1DB] focus-visible:outline-none focus-visible:border-brand-royal focus-visible:ring-2 focus-visible:ring-brand-royal/20 px-3 py-1 text-[14px] file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-[#9AA2AE] disabled:cursor-not-allowed disabled:bg-canvas disabled:opacity-60",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Input.displayName = "Input"

export { Input }
