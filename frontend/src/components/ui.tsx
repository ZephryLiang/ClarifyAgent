import type { ReactNode, TextareaHTMLAttributes } from "react";

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost";
}) {
  const base =
    "rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed";
  const styles =
    variant === "primary"
      ? "bg-indigo-600 hover:bg-indigo-500 text-white"
      : "bg-slate-700/60 hover:bg-slate-700 text-slate-200";
  return (
    <button className={`${base} ${styles}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={
        "w-full rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm text-slate-100 " +
        "placeholder-slate-500 focus:border-indigo-500 focus:outline-none " +
        (props.className ?? "")
      }
    />
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      {title ? <h3 className="mb-3 text-sm font-semibold text-slate-300">{title}</h3> : null}
      {children}
    </div>
  );
}

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-700 text-slate-200",
    green: "bg-emerald-600/80 text-white",
    red: "bg-red-600/80 text-white",
    amber: "bg-amber-600/80 text-white",
    indigo: "bg-indigo-600/80 text-white",
  };
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs ${tones[tone] ?? tones.slate}`}>
      {children}
    </span>
  );
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 75 ? "bg-emerald-500" : value >= 55 ? "bg-indigo-500" : value >= 35 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="mb-2">
      <div className="mb-1 flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span>{value.toFixed(1)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}
