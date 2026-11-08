import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-[14px] font-medium transition-[background-color,border-color,color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/40 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-brand-deep text-white shadow-[0_1px_2px_rgba(34,101,200,0.25)] hover:bg-[#1D58AF]",
        destructive:
          "bg-[#C0504D] text-white shadow-sm hover:bg-[#A8433F]",
        outline:
          "border border-line bg-white text-ink shadow-[0_1px_1px_rgba(32,36,43,0.04)] hover:border-[#D5DBE3] hover:bg-canvas",
        secondary:
          "bg-brand-pale text-brand-deep hover:bg-[#E1EEFD]",
        ghost: "text-ink hover:bg-brand-pale hover:text-brand-deep",
        link: "text-brand-royal underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-[8px] px-3 text-[13px]",
        lg: "h-10 rounded-[10px] px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
