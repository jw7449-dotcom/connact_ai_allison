"use client";
import {
  useEffect,
  useRef,
  useId,
  cloneElement,
  isValidElement,
  ReactElement,
} from "react";
import { X, ArrowUpRight, Search, LoaderCircle } from "lucide-react";
import { useApp } from "@/lib/context";
export function Nav({
  href,
  children,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  const { go } = useApp();
  return (
    <a
      href={href}
      className={className}
      onClick={(e) => {
        if (!e.metaKey && !e.ctrlKey) {
          e.preventDefault();
          void go(href);
        }
      }}
    >
      {children}
    </a>
  );
}
export function Avatar({
  name,
  large = false,
}: {
  name: string;
  large?: boolean;
}) {
  const n = name.charCodeAt(0) % 5;
  return (
    <span className={`avatar color-${n} ${large ? "large" : ""}`}>
      {name
        .split(" ")
        .slice(0, 2)
        .map((x) => x[0])
        .join("")}
    </span>
  );
}
export function Badge({
  children,
  tone = "gray",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Empty({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Search size={25} />
      </div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {children}
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  detail,
  children,
}: {
  eyebrow?: string;
  title: string;
  detail?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {detail && <p>{detail}</p>}
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export function Busy() {
  return <LoaderCircle className="spin" size={16} />;
}
export function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  const generated = useId();
  const child = children as ReactElement<{ id?: string }>;
  const id = child?.props?.id || generated;
  return (
    <div className={`field ${className}`}>
      <label htmlFor={id}>{label}</label>
      {isValidElement(child) ? cloneElement(child, { id }) : children}
    </div>
  );
}
export function Drawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="drawer"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="drawer-inner">
        <div className="drawer-head">
          <span>{title}</span>
          <button
            className="icon-button"
            aria-label="Close details"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
export function External({
  url,
  children,
}: {
  url: string;
  children: React.ReactNode;
}) {
  return /^https?:\/\//.test(url) ? (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="external"
    >
      {children}
      <ArrowUpRight size={13} />
    </a>
  ) : (
    <span className="muted">{children}</span>
  );
}
export function DateLabel({ value }: { value: string }) {
  const { locale } = useApp();
  return (
    <>
      {new Date(value).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })}
    </>
  );
}
