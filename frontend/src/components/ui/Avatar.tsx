import * as AvatarPrimitive from "@radix-ui/react-avatar"
import { cn } from "@/lib/utils"

const SIZES = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-12 w-12 text-base",
}

interface AvatarProps extends React.ComponentProps<typeof AvatarPrimitive.Root> {
  src?: string | null
  alt?: string
  fallback?: string
  size?: keyof typeof SIZES
}

function Avatar({ className, src, alt, fallback, size = "md", ...props }: AvatarProps) {
  const initials = fallback || alt?.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase() || "?"

  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      className={cn("relative flex shrink-0 overflow-hidden rounded-full", SIZES[size], className)}
      {...props}
    >
      {src && (
        <AvatarPrimitive.Image
          src={src}
          alt={alt || ""}
          className="aspect-square h-full w-full object-cover"
        />
      )}
      <AvatarPrimitive.Fallback
        className={cn(
          "flex h-full w-full items-center justify-center rounded-full bg-muted text-muted-foreground font-medium"
        )}
      >
        {initials}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  )
}

export { Avatar }
