import * as TooltipPrimitive from "@radix-ui/react-tooltip"
import { cn } from "@/lib/utils"

const TooltipProvider = TooltipPrimitive.Provider

function Tooltip({
  content,
  children,
  position = "top",
  className,
  delayDuration = 300,
}: {
  content: React.ReactNode
  children: React.ReactNode
  position?: "top" | "bottom" | "left" | "right"
  className?: string
  delayDuration?: number
}) {
  if (!content) return <>{children}</>

  return (
    <TooltipPrimitive.Root delayDuration={delayDuration}>
      <TooltipPrimitive.Trigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={position}
          sideOffset={4}
          className={cn(
            "z-50 rounded-md bg-popover border border-border px-3 py-1.5 text-xs text-popover-foreground shadow-md",
            "animate-scale-in",
            className
          )}
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-popover" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}

export { Tooltip, TooltipProvider }
export default Tooltip
