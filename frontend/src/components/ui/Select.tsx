import { cn } from "@/lib/utils"

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
}

function Select({ className, label, error, id, children, ...props }: SelectProps) {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined)
  return (
    <div>
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-foreground mb-1.5">
          {label}
        </label>
      )}
      <select
        id={selectId}
        data-slot="select"
        className={cn(
          "flex h-9 w-full rounded-lg border bg-muted px-3 py-2 text-sm text-foreground transition-colors",
          "focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent",
          "disabled:cursor-not-allowed disabled:opacity-50",
          error ? "border-destructive" : "border-input",
          className
        )}
        {...props}
      >
        {children}
      </select>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  )
}

export { Select }
export default Select
