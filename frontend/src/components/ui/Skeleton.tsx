import { cn } from "@/lib/utils"

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "circle" | "rect" | "badge"
  width?: number | string
  height?: number | string
}

function Skeleton({ className, variant = "text", width, height, ...props }: SkeletonProps) {
  const variants = {
    text: "h-4 w-full rounded",
    circle: "rounded-full",
    rect: "w-full rounded-lg",
    badge: "h-5 w-16 rounded-full",
  }

  const style: React.CSSProperties = {}
  if (width) style.width = typeof width === "number" ? `${width}px` : width
  if (height) style.height = typeof height === "number" ? `${height}px` : height

  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse bg-muted rounded", variants[variant], className)}
      style={style}
      {...props}
    />
  )
}

export { Skeleton }
export default Skeleton
