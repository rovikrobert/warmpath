import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

const Sheet = DialogPrimitive.Root
const SheetTrigger = DialogPrimitive.Trigger
const SheetPortal = DialogPrimitive.Portal
const SheetClose = DialogPrimitive.Close

function SheetOverlay({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      className={cn("fixed inset-0 z-50 bg-black/40 backdrop-blur-sm", className)}
      {...props}
    />
  )
}

function SheetContent({
  className,
  children,
  side = "right",
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { side?: "left" | "right" }) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <DialogPrimitive.Content
        className={cn(
          "fixed z-50 flex flex-col bg-card border-border shadow-xl transition-transform",
          side === "right" && "inset-y-0 right-0 border-l w-full sm:max-w-md animate-slide-over-in",
          side === "left" && "inset-y-0 left-0 border-r w-full sm:max-w-md",
          className
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex items-center justify-between border-b border-border px-5 py-4", className)}
      {...props}
    />
  )
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("text-lg font-semibold text-foreground", className)} {...props} />
}

function SheetBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex-1 overflow-y-auto px-5 py-4", className)} {...props} />
}

function SlideOver({
  open,
  onClose,
  title,
  children,
  width,
}: {
  open: boolean
  onClose: () => void
  title: React.ReactNode
  children: React.ReactNode
  width?: string
}) {
  return (
    <Sheet open={open} onOpenChange={(o: boolean) => !o && onClose()}>
      <SheetContent className={width}>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetClose className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </SheetClose>
        </SheetHeader>
        <SheetBody>{children}</SheetBody>
      </SheetContent>
    </Sheet>
  )
}

export { Sheet, SheetTrigger, SheetPortal, SheetOverlay, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetBody, SlideOver }
export default SlideOver
