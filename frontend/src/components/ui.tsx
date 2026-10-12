import { useEffect, useRef, useId } from "react";
import type {
  ReactNode,
  InputHTMLAttributes,
  ButtonHTMLAttributes,
  FormEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  X,
  CircleAlert,
  CheckCircle2,
  LoaderCircle,
  Home,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Page } from "../api/types";

export function Button({
  children,
  pending,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || pending}
      aria-busy={pending || undefined}
      className={`btn btn-${variant} ${props.className || ""}`}
    >
      {pending && (
        <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
      )}
      {children}
    </button>
  );
}
export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const generatedId = useId();
  const id = props.id || generatedId;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        {...props}
        id={id}
        aria-describedby={hint ? `${id}-hint` : props["aria-describedby"]}
      />
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
export function Select({
  label,
  name,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  name?: string;
  children: ReactNode;
}) {
  const generatedId = useId();
  const id = props.id || generatedId;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select {...props} id={id} name={name}>
        {children}
      </select>
    </div>
  );
}
export function Textarea({
  label,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  const generatedId = useId();
  const id = props.id || generatedId;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea rows={4} {...props} id={id} />
    </div>
  );
}
export function Feedback({
  error,
  success,
}: {
  error?: string | null;
  success?: string | null;
}) {
  return (
    <>
      {error && (
        <div role="alert" className="notice notice-error">
          <CircleAlert size={18} aria-hidden="true" />
          {error}
        </div>
      )}
      {success && (
        <div role="status" className="notice notice-success">
          <CheckCircle2 size={18} aria-hidden="true" />
          {success}
        </div>
      )}
    </>
  );
}
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={22} className="animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}
export function Resource<T>({
  value,
  children,
}: {
  value: { loading: boolean; error?: string; data?: T; reload: () => void };
  children: (data: T) => ReactNode;
}) {
  if (value.loading) return <Loading />;
  if (value.error)
    return (
      <div className="panel">
        <Feedback error={value.error} />
        <Button variant="secondary" onClick={value.reload}>
          Try again
        </Button>
      </div>
    );
  return value.data !== undefined ? <>{children(value.data)}</> : null;
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Home size={27} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function PageTitle({
  title,
  description,
  action,
  eyebrow,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <header className="page-title">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value}`}>{value.replaceAll("_", " ")}</span>
  );
}
export function Pagination({
  data,
  setPage,
}: {
  data: Pick<Page<unknown>, "total" | "page" | "page_size">;
  setPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  if (pages === 1) return null;
  return (
    <nav aria-label="Pagination" className="pagination">
      <Button
        variant="secondary"
        disabled={data.page <= 1}
        onClick={() => setPage(data.page - 1)}
      >
        <ArrowLeft size={16} />
        Previous
      </Button>
      <span>
        Page {data.page} of {pages}
      </span>
      <Button
        variant="secondary"
        disabled={data.page >= pages}
        onClick={() => setPage(data.page + 1)}
      >
        Next
        <ArrowRight size={16} />
      </Button>
    </nav>
  );
}
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog ref={ref} onCancel={onClose} className="modal" aria-label={title}>
      <div className="modal-head">
        <h2>{title}</h2>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function BackLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <Link className="back-link" to={to}>
      <ArrowLeft size={16} />
      {children}
    </Link>
  );
}
export function formData(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return new FormData(event.currentTarget);
}
export function text(data: FormData, name: string) {
  return String(data.get(name) || "").trim();
}
export function money(value: string | number) {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(Number(value));
}
export function day(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "Europe/Rome",
      }).format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value))
    : "Open-ended";
}
export function time(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Rome",
      }).format(new Date(value))
    : "Not scheduled";
}
export function today() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Rome",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((p) => p.type === type)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
export function localDatetime(value: string) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
