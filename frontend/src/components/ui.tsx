import type { ReactNode, TextareaHTMLAttributes } from "react";

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  size = "md",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md";
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors " +
    "disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3 py-1.5 text-sm" };
  const styles: Record<string, string> = {
    primary:
      "bg-[#2383e2] text-white hover:bg-[#1a73c7] shadow-sm",
    ghost:
      "text-[#37352f] hover:bg-[rgba(55,53,47,0.08)]",
    outline:
      "border border-[rgba(55,53,47,0.16)] text-[#37352f] hover:bg-[rgba(55,53,47,0.04)]",
    danger:
      "bg-[#eb5757] text-white hover:bg-[#d94444]",
  };
  return (
    <button
      type="button"
      className={`${base} ${sizes[size]} ${styles[variant]}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={
        "w-full rounded-md border border-[rgba(55,53,47,0.16)] bg-white p-3 text-sm text-[#37352f] " +
        "placeholder-[#9b9a97] focus:border-[#2383e2] focus:outline-none focus:ring-2 focus:ring-[rgba(35,131,226,0.2)] " +
        (props.className ?? "")
      }
    />
  );
}

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={
        "rounded-md border border-[rgba(55,53,47,0.09)] bg-white p-4 shadow-[0_1px_2px_rgba(15,15,15,0.04)] " +
        className
      }
    >
      {title ? (
        <h3 className="mb-3 text-xs font-medium text-[#787774]">{title}</h3>
      ) : null}
      {children}
    </div>
  );
}

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-[rgba(55,53,47,0.08)] text-[#37352f]",
    green: "bg-[rgba(46,125,50,0.12)] text-[#2e7d32]",
    red: "bg-[rgba(235,87,87,0.12)] text-[#c0392b]",
    amber: "bg-[rgba(245,158,11,0.15)] text-[#b45309]",
    indigo: "bg-[rgba(35,131,226,0.12)] text-[#2383e2]",
  };
  return (
    <span
      className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs ${tones[tone] ?? tones.slate}`}
    >
      {children}
    </span>
  );
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const color =
    value >= 75 ? "#2e7d32" : value >= 55 ? "#2383e2" : value >= 35 ? "#b45309" : "#eb5757";
  return (
    <div className="mb-3">
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-[#787774]">{label}</span>
        <span className="font-medium tabular-nums text-[#37352f]">{value.toFixed(0)}</span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-[rgba(55,53,47,0.08)]">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${Math.min(100, value)}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

export function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-[#2e7d32]" : "bg-[#b45309]"}`}
    />
  );
}

export function EmptyState({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-8 py-16 text-center">
      <div className="mb-3 text-3xl">{icon}</div>
      <p className="text-base font-medium text-[#37352f]">{title}</p>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-[#787774]">{description}</p>
    </div>
  );
}

export function Divider() {
  return <div className="my-4 border-t border-[rgba(55,53,47,0.09)]" />;
}
