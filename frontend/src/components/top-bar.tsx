import type { ComponentProps, ReactNode } from "react"

import { cn } from "@/lib/utils"

/**
 * The sticky bar above every view. The title slot is a run's name while it is
 * being written and its identity once it exists; actions sit on the right.
 */
function TopBar({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-20 flex h-[58px] shrink-0 items-center gap-2.5 border-b border-line bg-paper/92 px-4 backdrop-blur-md sm:gap-3.5 sm:px-6 lg:px-8">
      <div className="flex min-w-0 flex-1 items-baseline gap-2.5">{title}</div>
      {children}
    </header>
  )
}

function TopBarButton({ className, ...props }: ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-surface px-3.5 text-xs font-medium text-body transition-colors hover:bg-shell focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-default disabled:opacity-60",
        className
      )}
      {...props}
    />
  )
}

export { TopBar, TopBarButton }
