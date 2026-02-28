import { Toaster as SonnerToaster, toast } from "sonner"

function Toaster({ resolvedTheme = "dark" }: { resolvedTheme?: "light" | "dark" }) {
  return (
    <SonnerToaster
      theme={resolvedTheme as "light" | "dark"}
      position="top-right"
      toastOptions={{
        classNames: {
          toast: "border-border bg-card text-card-foreground",
          success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
          error: "border-destructive/30 bg-destructive/10 text-destructive",
          info: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
        },
      }}
    />
  )
}

export { Toaster, toast }

export function useToast() {
  return toast
}
