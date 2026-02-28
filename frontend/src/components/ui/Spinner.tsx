import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

const SIZES = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
}

interface SpinnerProps extends React.HTMLAttributes<SVGSVGElement> {
  size?: keyof typeof SIZES
}

function Spinner({ size = "md", className, ...props }: SpinnerProps) {
  return <Loader2 className={cn("animate-spin text-primary", SIZES[size], className)} {...props} />
}

export { Spinner }
export default Spinner
