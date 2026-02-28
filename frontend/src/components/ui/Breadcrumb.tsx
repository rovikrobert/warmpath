import { ChevronRight } from "lucide-react"
import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"

function Breadcrumb({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <nav aria-label="breadcrumb" className={cn("flex items-center", className)} {...props} />
}

function BreadcrumbList({ className, ...props }: React.HTMLAttributes<HTMLOListElement>) {
  return (
    <ol
      className={cn("flex items-center gap-1.5 text-sm text-muted-foreground flex-wrap", className)}
      {...props}
    />
  )
}

function BreadcrumbItem({ className, ...props }: React.HTMLAttributes<HTMLLIElement>) {
  return <li className={cn("inline-flex items-center gap-1.5", className)} {...props} />
}

function BreadcrumbLink({
  className,
  to,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <Link
      to={to}
      className={cn("text-muted-foreground hover:text-foreground transition-colors", className)}
      {...props}
    />
  )
}

function BreadcrumbPage({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      role="link"
      aria-current="page"
      aria-disabled="true"
      className={cn("text-foreground font-medium", className)}
      {...props}
    />
  )
}

function BreadcrumbSeparator({ className, ...props }: React.HTMLAttributes<HTMLLIElement>) {
  return (
    <li role="presentation" aria-hidden="true" className={cn("", className)} {...props}>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
    </li>
  )
}

export { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator }
