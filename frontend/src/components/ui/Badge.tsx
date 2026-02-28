import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary/15 text-primary",
        secondary: "bg-secondary text-secondary-foreground",
        destructive: "bg-destructive/15 text-destructive",
        outline: "border border-current/20 text-foreground",
        amber: "bg-amber-500/15 text-amber-400 dark:text-amber-400",
        emerald: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
        red: "bg-red-500/15 text-red-600 dark:text-red-400",
        blue: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
        purple: "bg-purple-500/15 text-purple-600 dark:text-purple-400",
        slate: "bg-muted text-muted-foreground",
        cyan: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
        indigo: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
        teal: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
        green: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      },
      size: {
        sm: "px-1.5 py-0.5 text-xs",
        default: "px-2 py-0.5 text-xs",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, size }), className)} {...props} />
}

export { Badge, badgeVariants }
export default Badge
