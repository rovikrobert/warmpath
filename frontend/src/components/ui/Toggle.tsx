import * as SwitchPrimitive from "@radix-ui/react-switch"
import { cn } from "@/lib/utils"

interface SwitchProps extends Omit<React.ComponentProps<typeof SwitchPrimitive.Root>, "onChange"> {
  label?: string
  description?: string
  onChange?: (checked: boolean) => void
}

function Switch({ className, label, description, checked, onChange, onCheckedChange, ...props }: SwitchProps) {
  const handleChange = onCheckedChange || onChange
  return (
    <div className="flex items-center justify-between">
      {(label || description) && (
        <div>
          {label && <p className="text-sm font-medium text-foreground">{label}</p>}
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
      )}
      <SwitchPrimitive.Root
        data-slot="switch"
        checked={checked}
        onCheckedChange={handleChange}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted",
          className
        )}
        {...props}
      >
        <SwitchPrimitive.Thumb
          className={cn(
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform mt-0.5",
            "data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0.5"
          )}
        />
      </SwitchPrimitive.Root>
    </div>
  )
}

export { Switch }
export { Switch as Toggle }
export default Switch
