import React from "react";
import { cn } from "../../lib/utils";
import { Button } from "./button";

export function IconActionButton({ className, variant = "secondary", ...props }) {
  return (
    <Button
      variant={variant}
      size="icon"
      className={cn("rounded-xl h-8 w-8", className)}
      {...props}
    />
  );
}
