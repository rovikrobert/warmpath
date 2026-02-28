import { cva, type VariantProps } from "class-variance-authority"
import { AlertCircle, CheckCircle2, Info, AlertTriangle, X } from "lucide-react"
import { cn } from "@/lib/utils"

const alertVariants = cva(
  "relative w-full rounded-lg border px-4 py-3 text-sm flex items-start gap-3 [&>svg]:shrink-0 [&>svg]:mt-0.5",
  {
    variants: {
      variant: {
        default: "bg-card text-foreground border-border",
        info: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 [&>svg]:text-blue-500",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 [&>svg]:text-emerald-500",
        warning: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 [&>svg]:text-amber-500",
        destructive: "border-destructive/30 bg-destructive/10 text-destructive [&>svg]:text-destructive",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

const ICONS = {
  default: Info,
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  destructive: AlertCircle,
}

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  icon?: React.ReactNode
  onDismiss?: () => void
}

function Alert({ className, variant = "default", icon, onDismiss, children, ...props }: AlertProps) {
  const Icon = ICONS[variant || "default"]
  return (
    <div role="alert" className={cn(alertVariants({ variant }), className)} {...props}>
      {icon || <Icon className="h-4 w-4" />}
      <div className="flex-1">{children}</div>
      {onDismiss && (
        <button onClick={onDismiss} className="shrink-0 text-current opacity-50 hover:opacity-100 transition-opacity">
          <X className="h-4 w-4" />
          <span className="sr-only">Dismiss</span>
        </button>
      )}
    </div>
  )
}

function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("font-medium leading-none tracking-tight", className)} {...props} />
}

function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm opacity-90 [&_p]:leading-relaxed", className)} {...props} />
}

export { Alert, AlertTitle, AlertDescription, alertVariants }
