import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface Step {
  label: string
  description?: string
}

interface StepperProps {
  steps: Step[]
  currentStep: number
  className?: string
}

function Stepper({ steps, currentStep, className }: StepperProps) {
  return (
    <div className={cn("flex items-center w-full", className)}>
      {steps.map((step, index) => {
        const isCompleted = index < currentStep
        const isCurrent = index === currentStep
        const isLast = index === steps.length - 1

        return (
          <div key={index} className={cn("flex items-center", !isLast && "flex-1")}>
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors",
                  isCompleted && "bg-primary text-primary-foreground",
                  isCurrent && "border-2 border-primary text-primary bg-primary/10",
                  !isCompleted && !isCurrent && "border-2 border-muted text-muted-foreground"
                )}
              >
                {isCompleted ? <Check className="h-4 w-4" /> : index + 1}
              </div>
              <span
                className={cn(
                  "text-xs font-medium text-center max-w-[80px]",
                  isCurrent ? "text-primary" : isCompleted ? "text-foreground" : "text-muted-foreground"
                )}
              >
                {step.label}
              </span>
              {step.description && (
                <span className="text-[10px] text-muted-foreground text-center max-w-[80px]">
                  {step.description}
                </span>
              )}
            </div>
            {!isLast && (
              <div className="flex-1 mx-2 mt-[-20px]">
                <div
                  className={cn(
                    "h-0.5 w-full transition-colors",
                    isCompleted ? "bg-primary" : "bg-muted"
                  )}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export { Stepper }
export type { Step, StepperProps }
