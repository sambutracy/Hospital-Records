import { useRef, type ReactNode } from "react";
import { ChevronDown, Menu } from "lucide-react";

export default function MobileNavigation({
  currentSection,
  children,
}: {
  currentSection: string;
  children: ReactNode;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  return (
    <details
      className="workspace-menu"
      ref={menu}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest("a")) {
          menu.current?.removeAttribute("open");
        }
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && menu.current?.open) {
          menu.current.open = false;
          menu.current.querySelector("summary")?.focus();
        }
      }}
    >
      <summary aria-label={`Main menu, current page ${currentSection}`}>
        <Menu size={20} aria-hidden="true" />
        <span>Menu</span>
        <span className="workspace-menu-current">{currentSection}</span>
        <ChevronDown
          className="workspace-menu-chevron"
          size={18}
          aria-hidden="true"
        />
      </summary>
      {children}
    </details>
  );
}
