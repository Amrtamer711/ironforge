import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/10 dark:focus-visible:ring-white/15 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "mmg-btn-primary bg-black text-white hover:bg-black/90 dark:bg-white dark:text-black dark:hover:bg-white/90 shadow-soft",
        secondary:
          "bg-black/5 text-black hover:bg-black/8 dark:bg-white/10 dark:text-white dark:hover:bg-white/15 shadow-soft",
        ghost:
          "bg-transparent hover:bg-black/5 text-black dark:text-white dark:hover:bg-white/10 shadow-soft",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-9 px-3",
        lg: "h-11 px-5",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export const Button = React.forwardRef(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
