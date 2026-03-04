import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const cardVariants = cva(
  "rounded-xl border border-border text-card-foreground transition-all duration-200",
  {
    variants: {
      variant: {
        default: "bg-card hover:-translate-y-0.5 hover:shadow-lg",
        glass: "glass border-border/50",
        static: "bg-card",
      },
    },
    defaultVariants: {
      variant: "static",
    },
  }
)

function Card({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof cardVariants>) {
  return (
    <div
      data-slot="card"
      className={cn(cardVariants({ variant, className }))}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-header" className={cn("border-b border-border px-5 py-4", className)} {...props} />
}

function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-content" className={cn("px-5 py-4", className)} {...props} />
}

function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-footer" className={cn("border-t border-border px-5 py-4", className)} {...props} />
}

function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-title" className={cn("text-lg font-semibold text-foreground", className)} {...props} />
}

function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-description" className={cn("text-sm text-muted-foreground", className)} {...props} />
}

export { Card, CardHeader, CardContent, CardFooter, CardTitle, CardDescription }
export default Card
